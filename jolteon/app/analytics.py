"""Markout, fee-adjusted markout, and execution edge for recorded fills.

All functions are pure and operate on the `decorated_order_fill` table (or
a subset of it) read via `jolteon.app.data.read_table` - nothing here
writes back to the database. Positive values are always favorable to the
market maker; negative values are adverse selection:

    BUY:  value = future_price - execution_price
    SELL: value = execution_price - future_price

`future_price` is the horizon fair price for markout, or the fair price at
fill time for edge.
"""

import pandas as pd

HORIZONS = ("100ms", "1s", "5s", "30s")

_SIDE_DIRECTION = {"BUY": 1.0, "SELL": -1.0}


def _signed(fills: pd.DataFrame, execution_price: pd.Series) -> pd.Series:
    direction = fills["side"].map(_SIDE_DIRECTION)
    return direction * (execution_price - fills["fill_price"])


def compute_markout(fills: pd.DataFrame, horizon: str) -> pd.Series:
    """Signed USD markout at `horizon` after each fill.

    NaN wherever that horizon's fair price hasn't backfilled yet.
    """
    return _signed(fills, fills[f"fair_price_{horizon}"])


def compute_net_markout(markout: pd.Series, fee: pd.Series) -> pd.Series:
    """Markout after subtracting the fee paid on the fill."""
    return markout - fee


def compute_edge(fills: pd.DataFrame) -> pd.Series:
    """Signed USD execution edge: how far the fill price sat from fair
    value at the moment of execution, in the market maker's favor."""
    return _signed(fills, fills["fair_price_at_fill"])


def usd_to_bps(usd: pd.Series, execution_price: pd.Series) -> pd.Series:
    """A USD amount as basis points of the execution price."""
    return usd / execution_price * 10_000
