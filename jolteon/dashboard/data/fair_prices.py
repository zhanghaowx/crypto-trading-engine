"""Reads of the fair-price series an engine records as it quotes."""

import sqlite3

import pandas as pd

from jolteon.dashboard.data.sqlite import database_exists

FAIR_PRICES = "fair_price"


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
