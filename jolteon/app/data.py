"""Data access helpers shared by the dashboard's pages.

Reads from the SQLite database that SignalRecorder writes into; never
talks to the running engine directly.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.engine.core.storage import paths
from jolteon.engine.core.storage.exchange_instrument_directory_discovery import (  # noqa: E501
    discover_exchange_instrument_directories,
)

# Rows already fetched, keyed by (database, table), for as long as this
# viewer's session lasts.
_CACHE_KEY = "_table_cache"

# Alias for the row id, named so it cannot collide with a recorded column.
_ROWID = "_jolteon_rowid"

# A session left open long enough would otherwise grow this cache forever;
# past this many rows, the oldest are dropped in favor of a bounded
# footprint, the same trade-off SQLiteHandler already makes for the logs
# table.
_MAX_CACHED_ROWS = 100_000

# How far back a keyed table is re-read for rows the engine may have
# rewritten in place under their key, rather than appended.
_REWRITABLE_ROWS = 5_000

# Markouts are joined per fill against the fair-price series on
# (symbol, model, timestamp). SignalRecorder declares no indexes - it
# records, it does not know what will be asked of the recording - so
# without this each fill scans the whole series and the join is quadratic
# in the length of the session.
FAIR_PRICES = "fair_price"
_FAIR_PRICE_LOOKUP_INDEX = "jolteon_fair_price_lookup"

# Paths whose index this process has already seen to, so a refresh does
# not ask the recording about its schema several times a second.
_indexed_paths: set[str] = set()


def reset_table_cache() -> None:
    """Forget every row read so far, so the next read starts from scratch."""
    st.session_state.pop(_CACHE_KEY, None)


def database_exists(db_path: str) -> bool:
    """
    Whether there is a database at `db_path` to read.

    An empty path is not one: `Path("")` is the directory the dashboard
    was started in, which exists, and every reader here would take that
    for a recording with nothing in it rather than for the engine that
    has not started.
    """
    return bool(db_path) and Path(db_path).exists()


def _has_primary_key(conn: sqlite3.Connection, table: str) -> bool:
    return any(row[5] for row in conn.execute(f'PRAGMA table_info("{table}")'))


def _max_rowid(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f'SELECT MAX(rowid) FROM "{table}"').fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def max_rowid(db_path: str, table: str) -> int:
    """The highest row id in `table`, or zero where the recording has no
    such table to have one."""
    if not database_exists(db_path):
        return 0
    conn = sqlite3.connect(db_path)
    try:
        return _max_rowid(conn, table)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return 0
    finally:
        conn.close()


def last_rowid_where(db_path: str, table: str, column: str) -> int | None:
    """
    Returns: The row id of the last recorded row whose `column` is true,
    or nothing where no row is.
    """
    if not database_exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            f'SELECT MAX(rowid) FROM "{table}" WHERE "{column}"'
        ).fetchone()
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return None
    finally:
        conn.close()
    return int(row[0]) if row and row[0] is not None else None


def read_after(
    db_path: str, table: str, rowid: int, run_id: str | None = None
) -> tuple[pd.DataFrame, int]:
    """
    Returns: The rows recorded after `rowid`, oldest first, and the row
    id of the last of them - `rowid` again where there are none.

    Unlike `read_table` this holds nothing between calls and is bounded
    by what the caller asks for, which is what a reader replaying a
    recording from a point in it needs: the general cache keeps only the
    most recent rows, and the row being replayed from is usually older
    than that.
    """
    if not database_exists(db_path):
        return pd.DataFrame(), rowid
    conn = sqlite3.connect(db_path)
    try:
        run_clause = " AND run_id = ?" if run_id is not None else ""
        params = (rowid, run_id) if run_id is not None else (rowid,)
        frame = pd.read_sql(
            f'SELECT rowid AS "{_ROWID}", * FROM "{table}" '
            f"WHERE rowid > ?{run_clause}",
            conn,
            params=params,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame(), rowid
    finally:
        conn.close()
    if frame.empty:
        return frame, rowid
    return frame.drop(columns=_ROWID), int(frame[_ROWID].iloc[-1])


def read_table(db_path: str, table: str) -> pd.DataFrame:
    """
    Everything recorded in `table`.

    The engine appends as it runs, so each refresh reads only the rows
    added since the last one and reuses what this session already holds.
    Read whole every time, a dashboard left open would re-read the entire
    session's recording every few seconds, on the same machine the engine
    is trading from, and the cost would climb all day.
    """
    if not database_exists(db_path):
        return pd.DataFrame()

    cache = st.session_state.setdefault(_CACHE_KEY, {})
    frame, cursor = cache.get((db_path, table), (pd.DataFrame(), 0))

    conn = sqlite3.connect(db_path)
    try:
        if _has_primary_key(conn, table):
            # A row under a primary key can be rewritten in place, and an
            # update leaves the row id untouched - so a cursor alone would
            # carry stale copies of the rows that changed. Only the recent
            # ones do change: a fill is rewritten while its markouts
            # resolve, and the longest horizon is half a minute. So the
            # tail is read again and the rest is kept, which holds the
            # cost flat instead of re-reading the session every refresh.
            top = _max_rowid(conn, table)
            if cursor > top:
                # The recording was replaced and the row ids started over.
                frame, cursor = pd.DataFrame(), 0
            settled = (
                frame[frame[_ROWID] <= top - _REWRITABLE_ROWS]
                if _ROWID in frame.columns
                else pd.DataFrame()
            )
            fresh = pd.read_sql(
                f'SELECT rowid AS "{_ROWID}", * FROM "{table}" '
                f"WHERE rowid > ?",
                conn,
                params=(max(top - _REWRITABLE_ROWS, 0),),
            )
            frame = (
                fresh
                if settled.empty
                else pd.concat([settled, fresh], ignore_index=True)
            )
            cursor = top
            if len(frame) > _MAX_CACHED_ROWS:
                frame = frame.iloc[-_MAX_CACHED_ROWS:].reset_index(drop=True)
            cache[(db_path, table)] = (frame, cursor)
            return frame.drop(columns=_ROWID).copy(deep=False)
        else:
            if cursor > _max_rowid(conn, table):
                # The recording was replaced and the row ids started over
                frame, cursor = pd.DataFrame(), 0

            fresh = pd.read_sql(
                f'SELECT rowid AS "{_ROWID}", * FROM "{table}" '
                f"WHERE rowid > ?",
                conn,
                params=(cursor,),
            )
            if not fresh.empty:
                cursor = int(fresh[_ROWID].iloc[-1])
                fresh = fresh.drop(columns=_ROWID)
                frame = (
                    fresh
                    if frame.empty
                    else pd.concat([frame, fresh], ignore_index=True)
                )
                if len(frame) > _MAX_CACHED_ROWS:
                    frame = frame.iloc[-_MAX_CACHED_ROWS:].reset_index(
                        drop=True
                    )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()

    cache[(db_path, table)] = (frame, cursor)

    # Shallow copy: pages add columns to what they get back, and that must
    # not pile up on the frame kept for the next refresh. It copies the
    # column index, not the rows.
    return frame.copy(deep=False)


def ensure_fair_price_lookup_index(db_path: str) -> bool:
    """
    Create the fair-price lookup index if the recording has no such index
    yet, and report whether one is now there to be used.

    The engine owns this file and may hold it locked; a recording that
    cannot be indexed right now still answers, only slowly, so a failure
    here is not worth surfacing to the viewer.
    """
    if not database_exists(db_path):
        return False
    if db_path in _indexed_paths:
        return True
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS "{_FAIR_PRICE_LOOKUP_INDEX}" '
            f'ON "{FAIR_PRICES}" (symbol, model, timestamp)'
        )
        conn.commit()
    except sqlite3.Error:
        return False
    else:
        _indexed_paths.add(db_path)
        return True
    finally:
        conn.close()


def read_fair_prices_for_fills(
    db_path: str,
    fills: pd.DataFrame,
    *,
    max_horizon_seconds: float,
    max_lag_seconds: float,
) -> pd.DataFrame:
    """Fair-price observations needed to derive markouts for fills.

    The recent-fills card only displays a page at a time. Querying the
    timestamp window around those fills avoids loading a session's entire
    fair-price stream merely to derive a handful of visible rows.
    """
    required = {"timestamp", "symbol", "fair_price_model"}
    if fills.empty or not required.issubset(fills.columns):
        return pd.DataFrame()

    timestamps = pd.to_numeric(fills["timestamp"], errors="coerce").dropna()
    symbols = tuple(str(v) for v in fills["symbol"].dropna().unique())
    models = tuple(str(v) for v in fills["fair_price_model"].dropna().unique())
    if (
        timestamps.empty
        or not symbols
        or not models
        or not database_exists(db_path)
    ):
        return pd.DataFrame()

    start = float(timestamps.min()) - max_lag_seconds
    end = float(timestamps.max()) + max_horizon_seconds + max_lag_seconds
    symbol_marks = ", ".join("?" for _ in symbols)
    model_marks = ", ".join("?" for _ in models)
    params = (start, end, *symbols, *models)

    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql(
            f'SELECT rowid AS "_jolteon_rowid", * FROM "fair_price" '
            f"WHERE timestamp BETWEEN ? AND ? "
            f"AND symbol IN ({symbol_marks}) "
            f"AND model IN ({model_marks}) "
            f"ORDER BY timestamp, rowid",
            conn,
            params=params,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()


@dataclass(frozen=True)
class RecordedEngineRun:
    """One EngineRun as the dashboard reads it back from a recording."""

    run_id: str
    exchange: str
    symbol: str
    started_at: datetime
    ended_at: datetime | None
    status: str


def _recorded_datetime(value) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


def engine_runs(db_path: str) -> list[RecordedEngineRun]:
    """Every recorded run, newest first, as "stopped", "interrupted" or
    "open".

    A run with no recorded end that a later run supersedes was
    interrupted: one engine trades one symbol, so the next run starting
    is proof this one is gone. The newest such run is only "open" - a
    process that dies never records its own end, so the recording alone
    cannot tell it from one still going.
    """
    if not database_exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = pd.read_sql(
            "SELECT run_id, exchange, symbol, started_at, ended_at "
            'FROM "engine_run" ORDER BY started_at DESC, rowid DESC',
            conn,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return []
    finally:
        conn.close()

    result = []
    for position, (_, row) in enumerate(rows.iterrows()):
        ended = _recorded_datetime(row["ended_at"])
        if ended is not None:
            status = "stopped"
        elif position == 0:
            status = "open"
        else:
            status = "interrupted"
        started = _recorded_datetime(row["started_at"])
        if started is None:
            continue
        result.append(
            RecordedEngineRun(
                run_id=str(row["run_id"]),
                exchange=str(row["exchange"]),
                symbol=str(row["symbol"]),
                started_at=started,
                ended_at=ended,
                status=status,
            )
        )
    return result


def latest_engine_run(db_path: str) -> RecordedEngineRun | None:
    """The newest engine process recorded in this database."""
    runs = engine_runs(db_path)
    return runs[0] if runs else None


def read_run_table(
    db_path: str, table: str, run_id: str | None
) -> pd.DataFrame:
    """A cached table restricted to one engine run when one is known."""
    frame = read_table(db_path, table)
    if run_id is None:
        return frame
    if "run_id" not in frame.columns:
        return frame.iloc[0:0].copy(deep=False)
    return frame[frame["run_id"] == run_id].copy(deep=False)


@dataclass(frozen=True)
class EngineDatabase:
    """One engine recording identified by exchange and canonical symbol."""

    path: str
    exchange: str
    symbol: str
    log_path: str
    legacy: bool = False

    @property
    def key(self) -> str:
        venue = paths.exchange_directory_name(self.exchange)
        return f"{venue}:{self.symbol}"

    @property
    def label(self) -> str:
        return f"{self.exchange} · {self.symbol}"


# How long a scan of the root is reused for. Below the shortest refresh
# interval the Live page offers, so an auto-refresh still picks up an
# engine that has just started, and above a burst of widget clicks, so
# working through a page does not reopen every engine's recording on each
# one. Nothing else invalidates this: a directory appearing on disk is
# not observable without looking for it.
#
# A caller that compares one scan against another within a single run
# also depends on the reuse: read live, the two would disagree by however
# long the first took.
SCAN_SECONDS = 2.0


@st.cache_data(ttl=SCAN_SECONDS, show_spinner=False)
def engine_databases(root: str) -> list[EngineDatabase]:
    """
    Returns: One entry per symbol something has been recorded for under
    `root`, each naming that instrument's recording and its log database.

    Every engine writes under a directory named after the symbol it
    trades, so the symbols on offer are the directories present. Reading
    the directory rather than matching file names against a pattern is
    also what keeps a log database from being taken for a recording of
    its own: it is a file inside a symbol's directory, not another one
    beside it.
    """
    databases = []
    for instrument in discover_exchange_instrument_directories(root):
        recording = str(instrument.path / f"{paths.LIVE}.sqlite")
        databases.append(
            EngineDatabase(
                path=recording,
                exchange=instrument.exchange,
                symbol=_recorded_symbol(recording, instrument.symbol),
                log_path=str(instrument.path / f"{paths.LIVE}.log.sqlite"),
                legacy=instrument.legacy,
            )
        )
    return databases


def _recorded_symbol(db_path: str, directory_symbol: str) -> str:
    """
    Returns: The symbol this recording is of, preferring what was
    recorded over the directory it was recorded in - the directory name
    is a spelling the engine chose, while a recorded tick names the pair
    as the venue does.
    """
    latest = read_latest_row(db_path, "bbo_feed")
    if latest is not None and latest.get("symbol"):
        return str(latest["symbol"])
    return directory_symbol


def as_datetime(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column, unit="s", utc=True)


def read_latest_row(db_path: str, table: str) -> pd.Series | None:
    """
    The most recently recorded row of `table`, or None if there isn't one.

    Reads only that one row from disk instead of going through `read_table`,
    for callers that only ever look at the tail - `read_table` would hold
    every row the session has seen just to answer that.
    """
    if not database_exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    try:
        frame = pd.read_sql(
            f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT 1', conn
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return None
    finally:
        conn.close()

    return None if frame.empty else frame.iloc[0]


def count_matching(
    db_path: str, table: str, column: str, values: tuple[str, ...]
) -> int:
    """
    How many rows of `table` carry one of `values` in `column`.

    Counted in the database rather than by reading the rows: the caller
    that needs this wants a number for every engine at once, and the
    table it asks about is the log, which is the largest one recorded.
    """
    if not database_exists(db_path):
        return 0

    conn = sqlite3.connect(db_path)
    try:
        placeholders = ", ".join("?" * len(values))
        found = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" '
            f'WHERE "{column}" IN ({placeholders})',
            values,
        ).fetchone()
        return int(found[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def read_latest_per_group(
    db_path: str,
    table: str,
    group_column: str,
    run_id: str | None = None,
) -> pd.DataFrame:
    """
    The most recently recorded row of `table` for each distinct value of
    `group_column` - the last heartbeat per sender, the last order per
    side, and so on - without reading every row to find it.
    """
    if not database_exists(db_path):
        return pd.DataFrame()

    conn = sqlite3.connect(db_path)
    try:
        where = " WHERE run_id = ?" if run_id is not None else ""
        params = (run_id,) if run_id is not None else ()
        frame = pd.read_sql(
            f'SELECT * FROM "{table}" WHERE rowid IN '
            f'(SELECT MAX(rowid) FROM "{table}"{where} '
            f'GROUP BY "{group_column}")',
            conn,
            params=params,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()

    return frame
