"""Data access helpers shared by the dashboard's pages.

Reads from the SQLite database that SignalRecorder writes into; never
talks to the running engine directly.
"""

import sqlite3
from dataclasses import dataclass
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
            # update leaves the row id untouched, so there is no cursor to
            # carry. These tables are bounded by their key's cardinality
            # rather than tick rate.
            frame = pd.read_sql(f'SELECT * FROM "{table}"', conn)
            cursor = 0
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
    latest = read_latest_row(db_path, "ticker_feed")
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
    db_path: str, table: str, group_column: str
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
        frame = pd.read_sql(
            f'SELECT * FROM "{table}" WHERE rowid IN '
            f'(SELECT MAX(rowid) FROM "{table}" GROUP BY "{group_column}")',
            conn,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()

    return frame
