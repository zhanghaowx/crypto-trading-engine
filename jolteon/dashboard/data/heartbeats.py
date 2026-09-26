"""Reads of the heartbeats an engine's components record as they run."""

import sqlite3
import time

import pandas as pd

from jolteon.dashboard.data.sqlite import database_exists

HEARTBEATS = "heartbeat"


def recent_heartbeats(
    db_path: str, *, since_seconds: float, now: float | None = None
) -> pd.DataFrame:
    """
    Returns: The `timestamp` and `sender` of every heartbeat recorded in
    the last `since_seconds` before `now` (the wall clock, unless given),
    oldest first - and nothing where the recording or its heartbeat
    table is missing.

    Asked of the recording rather than read through `read_table`: a
    session's heartbeats run to thousands of rows an hour, and the few
    minutes a history shows are all a reader ever wants of them.
    """
    if not database_exists(db_path):
        return pd.DataFrame()
    cutoff = (time.time() if now is None else now) - since_seconds
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql(
            f'SELECT timestamp, sender FROM "{HEARTBEATS}" '
            "WHERE timestamp > ? ORDER BY timestamp, rowid",
            conn,
            params=(cutoff,),
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()
