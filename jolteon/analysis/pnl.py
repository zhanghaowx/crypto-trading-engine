"""What a session's fills earned, on the two bases that differ.

Net cash flow counts what has moved in and out; realized PnL counts only
the round trips that have closed, leaving whatever is still held as an
unrealized gain rather than a loss.

Marked PnL - cash plus what is still held, valued at the mid - is worked
out both as it stands now and bucket by bucket over the session.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from jolteon.analysis.markouts import SIDE_DIRECTION

# Fill quantities are floats, so a position that has been fully closed out
# rarely lands exactly on zero.
POSITION_EPSILON = 1e-12


def _time_column(fills: pd.DataFrame) -> str:
    """The venue's own time for the fill if the recording has it, else the
    time the recorder saw it - every recorded table has `timestamp`."""
    preferred = "transaction_timestamp"
    return preferred if preferred in fills.columns else "timestamp"


def signed_cash_flow(fills: pd.DataFrame) -> pd.Series:
    """Cash each fill moved, before fees: positive when selling brings
    cash in, negative when buying pays it out."""
    direction = fills["side"].map(SIDE_DIRECTION)
    return -direction * fills["fill_price"] * fills["fill_qty"]


def _mid(bbo: pd.DataFrame) -> pd.Series:
    """The mid of each recorded `bbo_feed` row: the price inventory is
    marked at."""
    return (bbo["bid_price"] + bbo["ask_price"]) / 2


def pnl_by_symbol(
    totals: pd.DataFrame, latest_mid: pd.DataFrame
) -> pd.DataFrame:
    """`totals` - a position and a net cash flow per symbol, summed by
    the recording - marked to market.

    Net cash flow alone looks worse than reality while inventory is still
    held: the cash spent buying it shows up as an outflow with nothing
    offsetting it. Held inventory is marked at the latest mid price too, to
    match PositionManager.total_pnl in the engine. `latest_mid` is the last
    `bbo_feed` row per symbol (see `read_latest_per_group`), not the
    whole table - a mark price only ever needs the current one.
    """
    by_symbol = totals.copy()
    if not latest_mid.empty:
        mark_price = pd.Series(
            _mid(latest_mid).values, index=latest_mid["symbol"]
        )
    else:
        mark_price = pd.Series(dtype=float)
    by_symbol["mark_price"] = by_symbol.index.map(mark_price)
    by_symbol["inventory_value"] = by_symbol["position"] * by_symbol[
        "mark_price"
    ].fillna(0)
    by_symbol["total_pnl"] = (
        by_symbol["net_cash"] + by_symbol["inventory_value"]
    )
    return by_symbol


@dataclass(frozen=True)
class Realized:
    """What the closed round trips have earned so far, and what each
    symbol is still holding and at what average cost - everything needed
    to carry on from here when more fills are recorded."""

    total: float = 0.0
    holdings: Mapping[str, tuple[float, float]] = field(default_factory=dict)


def fold_fills(state: Realized, fills: pd.DataFrame) -> Realized:
    """
    `state` carried forward over `fills`, on an average-cost basis.

    Unlike net cash flow, acquiring inventory is not a loss here: a fill
    only contributes once it is traded back out again. Fees are charged
    as they are paid, so what is left over - total PnL minus this - is
    the unrealized gain sitting in open inventory.

    Written as a fold rather than a walk over the whole table because
    that is what lets a refresh pick up where the last one left off: a
    session's fills are walked once between them, not once each.
    """
    total = state.total
    holdings = dict(state.holdings)
    ordered = fills.sort_values(_time_column(fills))
    for fill in ordered.itertuples():
        position, avg_cost = holdings.get(fill.symbol, (0.0, 0.0))
        signed = fill.fill_qty if fill.side == "BUY" else -fill.fill_qty
        total -= fill.fee

        opening = position == 0.0 or (position > 0) == (signed > 0)
        if opening:
            # Adding to the position: fold the fill into the average.
            size = abs(position) + abs(signed)
            avg_cost = (
                abs(position) * avg_cost + abs(signed) * fill.fill_price
            ) / size
            position += signed
        else:
            # Trading against the position realizes the difference
            # between the fill price and the average cost of what it
            # closes out.
            closed = min(abs(signed), abs(position))
            direction = 1.0 if position > 0 else -1.0
            total += closed * (fill.fill_price - avg_cost) * direction

            flipped = abs(signed) - closed > POSITION_EPSILON
            position += signed
            if flipped:
                # The remainder opens a new position the other way round.
                avg_cost = fill.fill_price
            elif abs(position) <= POSITION_EPSILON:
                position, avg_cost = 0.0, 0.0
        holdings[fill.symbol] = (position, avg_cost)
    return Realized(total, holdings)


def realized_pnl(fills: pd.DataFrame) -> float:
    """Profit on the round trips that have actually closed, over `fills`
    alone."""
    return fold_fills(Realized(), fills).total


_SERIES_COLUMNS = [
    "time",
    "cash",
    "position",
    "mark",
    "inventory_value",
    "marked_pnl",
]


def _bucket_start(epoch_seconds: pd.Series, freq: str) -> pd.Series:
    """The start, in UTC, of the `freq` bucket each time falls in."""
    return pd.to_datetime(epoch_seconds, unit="s", utc=True).dt.floor(freq)


def _flows_per_bucket(fills: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Cash moved and quantity taken on by the fills of each bucket that
    saw one, fees charged as they were paid."""
    if fills.empty:
        return pd.DataFrame(
            {
                "cash": pd.Series(dtype=float),
                "position": pd.Series(dtype=float),
            },
            index=pd.DatetimeIndex([], tz="UTC"),
        )
    direction = fills["side"].map(SIDE_DIRECTION)
    flows = pd.DataFrame(
        {
            "cash": signed_cash_flow(fills) - fills["fee"],
            "position": direction * fills["fill_qty"],
        }
    )
    return flows.groupby(_bucket_start(fills[_time_column(fills)], freq)).sum()


def marked_pnl_series(
    fills: pd.DataFrame, mids: pd.DataFrame, *, freq: str
) -> pd.DataFrame:
    """How the marked PnL - cash moved by the fills plus what is still
    held, valued at the mid - stood at the end of every `freq` bucket
    from the first observation to the last.

    A bucket covers `[time, time + freq)`. `mark` is the last mid seen by
    the end of the bucket, carried forward over buckets without a tick,
    and stays NaN before the first mid: nothing has been observed to
    value the inventory with, so `inventory_value` and `marked_pnl` are
    NaN there too. `mids` is the recorded `bbo_feed`.
    """
    if mids.empty:
        return pd.DataFrame(columns=_SERIES_COLUMNS)
    ordered = mids.sort_values("timestamp", kind="stable")
    mark = (
        _mid(ordered).groupby(_bucket_start(ordered["timestamp"], freq)).last()
    )
    flows = _flows_per_bucket(fills, freq)
    observed = mark.index.union(flows.index)
    buckets = pd.date_range(observed.min(), observed.max(), freq=freq)

    series = pd.DataFrame(index=buckets)
    series["cash"] = flows["cash"].reindex(buckets, fill_value=0.0).cumsum()
    series["position"] = (
        flows["position"].reindex(buckets, fill_value=0.0).cumsum()
    )
    series["mark"] = mark.reindex(buckets).ffill()
    series["inventory_value"] = series["position"] * series["mark"]
    series["marked_pnl"] = series["cash"] + series["inventory_value"]
    return series.rename_axis("time").reset_index()


def fills_on_series(fills: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    """Where each fill sits on the marked PnL line: its own time and side,
    with the `marked_pnl` of the `series` bucket it fell in."""
    if fills.empty or series.empty:
        return pd.DataFrame(columns=["time", "side", "marked_pnl"])
    at_fill = pd.DataFrame(
        {
            "time": pd.to_datetime(
                fills[_time_column(fills)], unit="s", utc=True
            ),
            "side": fills["side"],
        }
    ).sort_values("time", kind="stable")
    return pd.merge_asof(
        at_fill,
        series[["time", "marked_pnl"]],
        on="time",
        direction="backward",
    )
