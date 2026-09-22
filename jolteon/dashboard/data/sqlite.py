"""Generic reads of the SQLite file an engine records into.

Nothing here knows what a row means; it answers "what is in this table"
and holds what a viewer's session has already read, so a dashboard left
open does not re-read the whole recording every few seconds.
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

# How far back a keyed table is re-read for rows the engine may have
# rewritten in place under their key, rather than appended.
_REWRITABLE_ROWS = 5_000


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


def recorded_through(
    frame: pd.DataFrame, *, time_column: str
) -> tuple[int, float]:
    """A cheap cache identity for a recorded table: how many rows it holds
    and how far through the session its last one is.

    Hashing the table itself costs about thirty milliseconds for a
    session's fills, which is a good part of what caching the derivation
    it keys is there to save. Both fills and fair prices are append-only,
    so a length and a latest timestamp pin a version of them exactly.
    """
    if frame.empty:
        return (0, 0.0)
    latest = (
        float(frame[time_column].iloc[-1]) if time_column in frame else 0.0
    )
    return (len(frame), latest)
