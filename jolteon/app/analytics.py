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


def compute_fill_edge(fills: pd.DataFrame) -> pd.Series:
    """Total USD edge kept on each fill: the per-unit edge scaled by how
    much was traded, less the fee paid to trade it."""
    return compute_edge(fills) * fills["fill_qty"] - fills["fee"]


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


InventoryBucket = tuple[str, float]

# (label, upper_bound) pairs in ascending upper_bound order. A BTC
# inventory level is classified into the first bucket whose upper_bound it
# does not exceed - the last bucket's upper_bound is a ceiling, never
# actually compared against for smaller values. Plain module constants
# rather than engine-side config, matching `_HORIZONS` in
# `post_trade_service.py`: this table lives entirely in the app layer, so
# there's nothing on the engine side for it to need to agree with.
DEFAULT_INVENTORY_BUCKETS: tuple[InventoryBucket, ...] = (
    ("Strongly short", -0.5),
    ("Moderately short", -0.1),
    ("Near neutral", 0.1),
    ("Moderately long", 0.5),
    ("Strongly long", float("inf")),
)


def classify_inventory_bucket(
    inventory: pd.Series,
    boundaries: tuple[InventoryBucket, ...] = DEFAULT_INVENTORY_BUCKETS,
) -> pd.Series:
    """Which named `boundaries` bucket each inventory level falls into."""
    labels = [label for label, _ in boundaries]
    edges = [-float("inf")] + [bound for _, bound in boundaries]
    return pd.cut(inventory, bins=edges, labels=labels, ordered=True)


def inventory_bucket_stats(
    fills: pd.DataFrame,
    boundaries: tuple[InventoryBucket, ...] = DEFAULT_INVENTORY_BUCKETS,
) -> pd.DataFrame:
    """Fill count, BUY/SELL split, markout, and net cash flow, one row per
    inventory bucket - classified by `inventory_before`, the position
    already held before each fill happened, rather than what the fill
    changed it to.

    `net_cash_flow` is just this bucket's own fills' cash in/out (price *
    quantity, net of fees) - not a real realized/inventory P&L split, which
    needs position state that outlives any single bucket (see the
    portfolio-level P&L decomposition planned separately).
    """
    bucket = classify_inventory_bucket(fills["inventory_before"], boundaries)
    edge = compute_edge(fills)
    signed_qty = fills["fill_qty"].where(
        fills["side"] == "BUY", -fills["fill_qty"]
    )
    cash_flow = (-fills["fill_price"] * signed_qty) - fills["fee"]

    rows = {}
    for label, group in fills.groupby(bucket, observed=True):
        group_edge = edge.loc[group.index]
        row = {
            "fill_count": len(group),
            "buy_count": int((group["side"] == "BUY").sum()),
            "sell_count": int((group["side"] == "SELL").sum()),
            "avg_edge": group_edge.mean(),
            "net_cash_flow": cash_flow.loc[group.index].sum(),
        }
        for horizon in HORIZONS:
            markout = compute_markout(group, horizon)
            row[f"avg_markout_{horizon}"] = markout.mean()
            row[f"median_markout_{horizon}"] = markout.median()
            row[f"avg_net_markout_{horizon}"] = compute_net_markout(
                markout, group["fee"]
            ).mean()
        rows[label] = row
    return pd.DataFrame.from_dict(rows, orient="index")
