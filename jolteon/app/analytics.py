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


def fair_price_movement(fills: pd.DataFrame, horizon: str) -> pd.Series:
    """Signed USD change in the fair price itself at `horizon` after each
    fill, independent of trade side.

    Unlike markout, this says nothing about execution quality - it
    measures whether the fair-price model tends to keep drifting after a
    fill, i.e. whether it has short-term predictive power.
    """
    return fills[f"fair_price_{horizon}"] - fills["fair_price_at_fill"]


def avg_fair_price_movement(fills: pd.DataFrame) -> pd.Series:
    """Average signed fair-price movement at each horizon, across every
    fill, indexed by horizon label."""
    return pd.Series(
        {
            horizon: fair_price_movement(fills, horizon).mean()
            for horizon in HORIZONS
        }
    )


def fill_quality_by_side(fills: pd.DataFrame) -> pd.DataFrame:
    """Fill count, average edge, and average gross/fee-adjusted markout at
    each horizon, broken out by BUY vs SELL - whether one side of the
    market is systematically worse than the other, indexed by side."""
    edge = compute_edge(fills)
    rows = {}
    for side, group in fills.groupby("side"):
        group_edge = edge.loc[group.index]
        row = {
            "fill_count": len(group),
            "avg_edge": group_edge.mean(),
            "avg_fee": group["fee"].mean(),
        }
        for horizon in HORIZONS:
            markout = compute_markout(group, horizon)
            row[f"avg_markout_{horizon}"] = markout.mean()
            row[f"avg_net_markout_{horizon}"] = compute_net_markout(
                markout, group["fee"]
            ).mean()
        rows[side] = row
    return pd.DataFrame.from_dict(rows, orient="index")
