"""Data access helpers shared by the dashboard's pages.

Reads from the SQLite database that SignalRecorder writes into; never
talks to the running engine directly.
"""

import sqlite3
from pathlib import Path

import pandas as pd


def read_table(db_path: str, table: str) -> pd.DataFrame:
    if not Path(db_path).exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            return pd.read_sql(f'SELECT * FROM "{table}"', conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()


def as_datetime(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column, unit="s", utc=True)


def latest_quotes(orders: pd.DataFrame) -> pd.DataFrame:
    """The most recent order the strategy sent for each side, if any."""
    if orders.empty:
        return orders
    return orders.sort_values("timestamp").groupby("side").tail(1)
