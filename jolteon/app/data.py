"""Data access helpers shared by the dashboard's pages.

Reads from the SQLite database that SignalRecorder writes into; never
talks to the running engine directly.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

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
    if not Path(db_path).exists():
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


def as_datetime(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column, unit="s", utc=True)


def read_latest_row(db_path: str, table: str) -> pd.Series | None:
    """
    The most recently recorded row of `table`, or None if there isn't one.

    Reads only that one row from disk instead of going through `read_table`,
    for callers that only ever look at the tail - `read_table` would hold
    every row the session has seen just to answer that.
    """
    if not Path(db_path).exists():
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


def read_latest_per_group(
    db_path: str, table: str, group_column: str
) -> pd.DataFrame:
    """
    The most recently recorded row of `table` for each distinct value of
    `group_column` - the last heartbeat per sender, the last order per
    side, and so on - without reading every row to find it.
    """
    if not Path(db_path).exists():
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
