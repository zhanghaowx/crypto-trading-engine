import json
import sqlite3
import time
from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS parameter_override (
    group_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (group_name, field_name, symbol)
);
CREATE TABLE IF NOT EXISTS parameter_change (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL,
    changed_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class ParameterOverride:
    group_name: str
    field_name: str
    symbol: str
    value: object


class ParameterStore:
    """
    The file a dashboard pushes tunables into and an engine reads them
    out of.

    Only the dashboard ever writes it. The engine opens it read-only, so
    the two processes can never contend for the same write lock - the
    same reason the engine's logs live in a database of their own.
    """

    def __init__(self, database_name: str):
        self._database_name = database_name
        self._reader: sqlite3.Connection | None = None

    def data_version(self) -> int | None:
        """
        Returns: A number that changes whenever another connection has
        committed, or None while the file cannot be read yet.

        Polling this instead of the rows themselves keeps a quiet engine
        down to one trivial query per tick. It only ever moves on a
        connection that stays open, so this deliberately reuses one
        rather than connecting per call.
        """
        return self._reading(
            lambda conn: int(
                conn.execute("PRAGMA data_version").fetchone()[0]
            ),
            default=None,
        )

    def read(self) -> list[ParameterOverride]:
        """
        Returns: Every stored override, or nothing at all if the file is
        missing or unreadable.

        A dashboard that has never pushed has not created the file yet,
        which is the engine's normal startup state rather than a fault.
        """
        rows = self._reading(
            lambda conn: conn.execute(
                "SELECT group_name, field_name, symbol, value "
                "FROM parameter_override"
            ).fetchall(),
            default=[],
        )

        overrides = []
        for group_name, field_name, symbol, value in rows:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            overrides.append(
                ParameterOverride(group_name, field_name, symbol, parsed)
            )
        return overrides

    def push(
        self,
        overrides: list[ParameterOverride],
        source: str = "dashboard",
    ) -> None:
        """
        Writes every given override and its history in one transaction,
        so an engine polling mid-push sees all of them or none.
        """
        now = time.time()
        with self._writable() as conn:
            conn.executescript(_SCHEMA)
            with conn:
                for override in overrides:
                    key = (
                        override.group_name,
                        override.field_name,
                        override.symbol,
                    )
                    previous = conn.execute(
                        "SELECT value FROM parameter_override WHERE "
                        "group_name = ? AND field_name = ? AND symbol = ?",
                        key,
                    ).fetchone()
                    encoded = json.dumps(override.value)
                    conn.execute(
                        "INSERT INTO parameter_override "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(group_name, field_name, symbol) "
                        "DO UPDATE SET value = excluded.value, "
                        "updated_at = excluded.updated_at",
                        (*key, encoded, now),
                    )
                    conn.execute(
                        "INSERT INTO parameter_change (group_name, field_name,"
                        " symbol, old_value, new_value, source, changed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            *key,
                            previous[0] if previous else None,
                            encoded,
                            source,
                            now,
                        ),
                    )

    def reset(
        self,
        group_name: str | None = None,
        source: str = "dashboard",
    ) -> None:
        """
        Drops overrides so the engine falls back to declared defaults,
        for one group or for everything.
        """
        now = time.time()
        with self._writable() as conn:
            conn.executescript(_SCHEMA)
            with conn:
                where = ""
                params: tuple[str, ...] = ()
                if group_name is not None:
                    where = " WHERE group_name = ?"
                    params = (group_name,)
                dropped = conn.execute(
                    "SELECT group_name, field_name, symbol, value "
                    "FROM parameter_override" + where,
                    params,
                ).fetchall()
                conn.execute("DELETE FROM parameter_override" + where, params)
                conn.executemany(
                    "INSERT INTO parameter_change (group_name, field_name, "
                    "symbol, old_value, new_value, source, changed_at) "
                    "VALUES (?, ?, ?, ?, NULL, ?, ?)",
                    [(*row, source, now) for row in dropped],
                )

    def changes(self, limit: int = 50) -> list[tuple]:
        """
        Returns: The most recent pushes, newest first.
        """
        return self._reading(
            lambda conn: conn.execute(
                "SELECT group_name, field_name, symbol, old_value, "
                "new_value, source, changed_at FROM parameter_change "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall(),
            default=[],
        )

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    def _reading(self, query, default):
        """
        Runs `query` on the shared read-only connection, reopening it
        next time if the file was missing, replaced or damaged - none of
        which is a fault worth stopping an engine for.
        """
        try:
            if self._reader is None:
                self._reader = self._read_only()
            return query(self._reader)
        except sqlite3.Error:
            self.close()
            return default

    def _read_only(self) -> sqlite3.Connection:
        # The poller owns this connection once started; only its own
        # first read happens on another thread, before it exists.
        return sqlite3.connect(
            f"file:{self._database_name}?mode=ro",
            uri=True,
            timeout=30,
            check_same_thread=False,
        )

    def _writable(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database_name, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def override_of(group_name: str, field_name: str, value: object):
    return ParameterOverride(group_name, field_name, ALL_SYMBOLS, value)
