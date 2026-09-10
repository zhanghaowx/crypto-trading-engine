"""A background thread that owns every write to one SQLite database.

The trading engine runs SQLite writes on the threads that produce the data:
the market data thread sends signals, and the engine's event loop hosts the
heartbeat tasks. Writing from those threads means a slow disk stalls the
feed, or delays heartbeats badly enough that healthy components look down.

`SQLiteWriter` moves all of it onto a thread of its own. Producers pay for a
single queue append and nothing else - no lock, no SQL, no DataFrame.
"""

import atexit
import queue
import sqlite3
import sys
import threading
from typing import Any

# Upper bound on how many rows one transaction may cover. The writer drains
# whatever is queued, so this only matters when producers outrun the disk;
# it caps how long a single commit can hold the write lock.
_MAX_BATCH = 5000


class _Flush:
    """Marker asking the writer to signal `event` once it has committed."""

    __slots__ = ("event",)

    def __init__(self) -> None:
        self.event = threading.Event()


class _Stop:
    """Marker asking the writer thread to exit after draining."""


class _Prune:
    """Marker asking the writer to trim a table down to its newest rows."""

    __slots__ = ("table", "keep_last")

    def __init__(self, table: str, keep_last: int) -> None:
        self.table = table
        self.keep_last = keep_last


class _Table:
    """What the writer knows about one table's schema."""

    __slots__ = ("columns", "primary_key")

    def __init__(self, columns: set[str], primary_key: str | None) -> None:
        self.columns = columns
        self.primary_key = primary_key


def _quote(identifier: str) -> str:
    """Quote a table or column name coming from a signal or payload field."""
    return '"' + identifier.replace('"', "") + '"'


class SQLiteWriter:
    """
    Serializes writes to a SQLite database onto a single background thread.

    Tables are created on first use and widened with ALTER TABLE when a
    payload grows a field, so a schema change costs one statement rather
    than a rewrite of everything already recorded.
    """

    def __init__(self, database_name: str):
        self._database_name = database_name
        self._queue: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._schema = dict[str, _Table]()
        # Writes happen off the caller's thread, so a failure has no call
        # stack to surface on. Hold the first one and re-raise it from
        # `flush`, which is the next point a caller is listening.
        self._error: BaseException | None = None
        self._error_lock = threading.Lock()
        self._closed = False

        self._thread = threading.Thread(
            name=f"SQLiteWriter({database_name})",
            target=self._run,
            daemon=True,
        )
        self._thread.start()

        atexit.register(self._close_quietly)

    def put(
        self,
        table: str,
        row: dict[str, Any],
        primary_key: str | None = None,
    ) -> None:
        """
        Hand one row to the writer thread.

        This is the only method the engine's hot paths call, and it does
        nothing but append to a queue.

        Args:
            table: Table to append to, created on first use.
            row: Column name to value. Rows in one table need not agree on
                 columns; missing ones are stored as NULL.
            primary_key: Column that identifies the row. When set, a later
                         row with the same value updates the stored one
                         instead of adding a duplicate.
        """
        self._queue.put((table, row, primary_key))

    def prune(self, table: str, keep_last: int) -> None:
        """
        Ask the writer to delete every row in `table` except the
        `keep_last` most recently inserted ones.

        Like `put`, this only appends to the queue; the deleting happens on
        the writer thread the next time it drains the queue.
        """
        self._queue.put(_Prune(table, keep_last))

    def flush(self) -> None:
        """
        Block until everything queued so far has been committed.

        Raises whatever the writer thread last failed with, so callers see
        write errors even though the write happened on another thread.
        """
        if self._thread.is_alive():
            marker = _Flush()
            self._queue.put(marker)
            # Poll rather than wait outright: a writer thread that dies
            # before reaching the marker would otherwise block forever.
            while not marker.event.wait(timeout=0.1):
                if not self._thread.is_alive():
                    break
        self._raise_pending_error()

    def close(self) -> None:
        """Flush anything outstanding and stop the writer thread."""
        if self._closed:
            return
        self._closed = True
        if self._thread.is_alive():
            self._queue.put(_Stop())
            self._thread.join(timeout=30)
        self._raise_pending_error()

    def _close_quietly(self) -> None:
        """
        Close at interpreter exit, where a raised error would only surface
        as a traceback from an atexit callback.
        """
        try:
            self.close()
        except BaseException as e:  # noqa: BLE001 - nothing left to handle
            print(
                f"Failed to write to {self._database_name}: {e}",
                file=sys.stderr,
            )

    def _raise_pending_error(self) -> None:
        with self._error_lock:
            error, self._error = self._error, None
        if error is not None:
            raise error

    def _record_error(self, error: BaseException) -> None:
        # Deliberately not logged: the logging handler writes through a
        # writer of its own, so logging a write failure risks feeding the
        # failure back into the queue that caused it.
        with self._error_lock:
            if self._error is None:
                self._error = error

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database_name)
        # Set first, so the journal mode switch below gets the same retry
        # window as every other statement.
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            # WAL lets the dashboard read while the engine writes; without
            # it a write takes an exclusive lock on the whole file and
            # readers time out. It is a property of the file, so this
            # survives reconnects.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            # Another connection is holding the database in its existing
            # journal mode. Recording still works; readers just contend.
            pass
        return conn

    def _run(self) -> None:
        try:
            conn = self._connect()
        except BaseException as e:  # noqa: BLE001 - reported via flush()
            self._record_error(e)
            self._drain_on_failure()
            return

        try:
            while True:
                if not self._process(conn, self._queue.get()):
                    return
        finally:
            conn.close()

    def _drain_on_failure(self) -> None:
        """Release anyone waiting in `flush` when the writer cannot run."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if isinstance(item, _Flush):
                item.event.set()
            elif isinstance(item, _Stop):
                return

    def _process(self, conn: sqlite3.Connection, first: Any) -> bool:
        """
        Write `first` plus everything already queued behind it.

        Returns False once a stop marker has been seen.
        """
        batch = dict[str, list[dict[str, Any]]]()
        primary_keys = dict[str, str | None]()
        flushes = list[_Flush]()
        prunes = list[_Prune]()
        item = first
        rows = 0
        stop = False

        while True:
            if isinstance(item, _Flush):
                flushes.append(item)
            elif isinstance(item, _Stop):
                stop = True
                break
            elif isinstance(item, _Prune):
                prunes.append(item)
            else:
                table, row, primary_key = item
                batch.setdefault(table, []).append(row)
                primary_keys.setdefault(table, primary_key)
                rows += 1
                if rows >= _MAX_BATCH:
                    break
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

        if batch or prunes:
            try:
                for table, table_rows in batch.items():
                    self._write(conn, table, table_rows, primary_keys[table])
                for prune in prunes:
                    self._prune(conn, prune.table, prune.keep_last)
                conn.commit()
            except BaseException as e:  # noqa: BLE001 - via flush()
                conn.rollback()
                # The batch is dropped: retrying a batch that SQLite has
                # already rejected would stall every row behind it.
                self._schema.clear()
                self._record_error(e)

        for marker in flushes:
            marker.event.set()

        return not stop

    def _write(
        self,
        conn: sqlite3.Connection,
        table: str,
        rows: list[dict[str, Any]],
        primary_key: str | None,
    ) -> None:
        # Union rather than the first row's keys: payloads in one table may
        # disagree on optional fields, and a column absent here is NULL.
        columns = list(dict.fromkeys(k for row in rows for k in row))
        if not columns:
            return

        effective_key = self._ensure_table(conn, table, columns, primary_key)
        if effective_key is not None:
            # Collapse repeated updates of the same key - a payload
            # carrying a PRIMARY_KEY may be re-sent many times - into the
            # one row that survives.
            latest = dict[Any, dict[str, Any]]()
            for row in rows:
                latest[row.get(effective_key)] = row
            rows = list(latest.values())

        names = ", ".join(_quote(c) for c in columns)
        placeholders = ", ".join("?" * len(columns))
        statement = (
            f"INSERT INTO {_quote(table)} ({names}) VALUES ({placeholders})"
        )
        if effective_key is not None:
            assignments = ", ".join(
                f"{_quote(c)}=excluded.{_quote(c)}"
                for c in columns
                if c != effective_key
            )
            if assignments:
                statement += (
                    f" ON CONFLICT({_quote(effective_key)}) "
                    f"DO UPDATE SET {assignments}"
                )
            else:
                statement += " ON CONFLICT DO NOTHING"

        conn.executemany(
            statement,
            [tuple(row.get(c) for c in columns) for row in rows],
        )

    def _prune(
        self, conn: sqlite3.Connection, table: str, keep_last: int
    ) -> None:
        # Nothing to trim if this writer has never inserted into `table`.
        if table not in self._schema:
            return
        conn.execute(
            f"DELETE FROM {_quote(table)} WHERE rowid NOT IN "
            f"(SELECT rowid FROM {_quote(table)} "
            f"ORDER BY rowid DESC LIMIT ?)",
            (keep_last,),
        )

    def _ensure_table(
        self,
        conn: sqlite3.Connection,
        table: str,
        columns: list[str],
        primary_key: str | None,
    ) -> str | None:
        """
        Create or widen `table`, and report the primary key it actually has.

        A database recorded before primary keys were declared keeps its
        original schema, so the key is taken from the table rather than
        from the payload.
        """
        known = self._schema.get(table)
        if known is None:
            info = conn.execute(
                f"PRAGMA table_info({_quote(table)})"
            ).fetchall()
            if info:
                known = _Table(
                    columns={row[1] for row in info},
                    primary_key=next((row[1] for row in info if row[5]), None),
                )
            else:
                # Columns are declared without a type: SQLite keeps each
                # value's own type, which is what the payloads carry.
                declarations = ", ".join(
                    _quote(c) + (" PRIMARY KEY" if c == primary_key else "")
                    for c in columns
                )
                conn.execute(f"CREATE TABLE {_quote(table)} ({declarations})")
                known = _Table(
                    columns=set(columns),
                    primary_key=(
                        primary_key if primary_key in columns else None
                    ),
                )
            self._schema[table] = known

        for column in columns:
            if column not in known.columns:
                conn.execute(
                    f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(column)}"
                )
                known.columns.add(column)

        return known.primary_key
