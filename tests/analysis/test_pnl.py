import pandas as pd
import pytest

from jolteon.analysis.pnl import (
    fills_on_series,
    marked_pnl_series,
    realized_pnl,
    signed_cash_flow,
)


def _fills(*trades) -> pd.DataFrame:
    """A fills table from `(side, price, quantity, fee)` tuples, in the
    order they were traded."""
    return pd.DataFrame(
        [
            {
                "transaction_timestamp": 1700000000 + index,
                "symbol": "BTC-USD",
                "side": side,
                "fill_price": price,
                "fill_qty": quantity,
                "fee": fee,
            }
            for index, (side, price, quantity, fee) in enumerate(trades)
        ]
    )


@pytest.mark.parametrize(
    "trades,expected",
    [
        # Inventory bought and still held realizes nothing but its fee.
        ((("BUY", 100.0, 1.0, 0.1),), -0.1),
        # A closed round-trip realizes the difference, less both fees.
        ((("BUY", 100.0, 1.0, 0.1), ("SELL", 110.0, 1.0, 0.1)), 9.8),
        # Selling half a position realizes half the gain over average cost.
        (
            (
                ("BUY", 100.0, 1.0, 0.0),
                ("BUY", 120.0, 1.0, 0.0),
                ("SELL", 130.0, 1.0, 0.0),
            ),
            20.0,
        ),
        # Shorts work the same way round.
        ((("SELL", 100.0, 1.0, 0.0), ("BUY", 90.0, 1.0, 0.0)), 10.0),
        # An oversized sell closes the long and opens a short at its price,
        # which the final buy then closes.
        (
            (
                ("BUY", 100.0, 1.0, 0.0),
                ("SELL", 110.0, 2.0, 0.0),
                ("BUY", 105.0, 1.0, 0.0),
            ),
            15.0,
        ),
    ],
)
def test_realized_pnl_counts_only_closed_round_trips(trades, expected):
    assert realized_pnl(_fills(*trades)) == pytest.approx(expected)


def test_realized_pnl_keeps_symbols_apart():
    fills = _fills(("BUY", 100.0, 1.0, 0.0), ("SELL", 110.0, 1.0, 0.0))
    fills.loc[1, "symbol"] = "ETH-USD"

    # The sell belongs to a different symbol, so it opens a short rather
    # than closing the BTC-USD long.
    assert realized_pnl(fills) == pytest.approx(0.0)


def test_buying_pays_cash_out_and_selling_brings_cash_in():
    fills = pd.DataFrame(
        {
            "side": ["BUY", "SELL"],
            "fill_price": [100.0, 200.0],
            "fill_qty": [2.0, 0.5],
        }
    )
    assert list(signed_cash_flow(fills)) == pytest.approx([-200.0, 100.0])


# 2023-11-14 22:13:20 UTC: a whole number of five-second buckets from the
# epoch, so the series below start on a bucket boundary.
T = 1700000000


def _utc(seconds: float) -> pd.Timestamp:
    return pd.Timestamp(seconds, unit="s", tz="UTC")


def _fills_at(*trades) -> pd.DataFrame:
    """A fills table from `(time, side, price, quantity, fee)` tuples."""
    return pd.DataFrame(
        [
            {
                "transaction_timestamp": time,
                "symbol": "BTC-USD",
                "side": side,
                "fill_price": price,
                "fill_qty": quantity,
                "fee": fee,
            }
            for time, side, price, quantity, fee in trades
        ]
    )


def _mids(*ticks) -> pd.DataFrame:
    """A `bbo_feed` table from `(time, bid, ask)` tuples."""
    return pd.DataFrame(
        [
            {
                "timestamp": time,
                "symbol": "BTC-USD",
                "bid_price": bid,
                "ask_price": ask,
            }
            for time, bid, ask in ticks
        ]
    )


def test_marked_pnl_series_values_held_inventory_at_the_bucket_mid():
    mids = _mids(
        (T, 99.0, 101.0), (T + 5, 109.0, 111.0), (T + 10, 119.0, 121.0)
    )
    fills = _fills_at(
        (T + 1, "BUY", 100.0, 2.0, 0.0), (T + 6, "SELL", 110.0, 1.0, 0.0)
    )

    series = marked_pnl_series(fills, mids, freq="5s")

    # By hand: buying two at 100 pays 200 out, and marked at a mid of 100
    # they are worth exactly what they cost. Selling one at 110 brings
    # 110 back, so cash is -90 with one still held: worth 110 at that
    # bucket's mid, then 120 in the bucket after, which saw no fill.
    assert list(series["time"]) == [_utc(T), _utc(T + 5), _utc(T + 10)]
    assert list(series["cash"]) == pytest.approx([-200.0, -90.0, -90.0])
    assert list(series["position"]) == pytest.approx([2.0, 1.0, 1.0])
    assert list(series["mark"]) == pytest.approx([100.0, 110.0, 120.0])
    assert list(series["inventory_value"]) == pytest.approx(
        [200.0, 110.0, 120.0]
    )
    assert list(series["marked_pnl"]) == pytest.approx([0.0, 20.0, 30.0])


def test_mark_carries_forward_over_buckets_without_a_tick():
    mids = _mids((T, 99.0, 101.0), (T + 15, 103.0, 105.0))
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_series(fills, mids, freq="5s")

    assert list(series["time"]) == [
        _utc(T + offset) for offset in range(0, 20, 5)
    ]
    assert list(series["mark"]) == pytest.approx([100.0, 100.0, 100.0, 104.0])
    assert list(series["marked_pnl"]) == pytest.approx([0.0, 0.0, 0.0, 4.0])


def test_mark_is_the_last_mid_of_the_bucket_whatever_order_rows_came_in():
    mids = _mids((T + 2, 101.0, 103.0), (T, 99.0, 101.0))

    series = marked_pnl_series(pd.DataFrame(), mids, freq="5s")

    assert list(series["mark"]) == pytest.approx([102.0])


def test_bucket_before_the_first_mid_has_nothing_to_value_inventory_with():
    mids = _mids((T + 5, 101.0, 103.0))
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_series(fills, mids, freq="5s")

    before, after = series.iloc[0], series.iloc[1]
    assert before["cash"] == -100.0
    assert before["position"] == 1.0
    assert pd.isna(before[["mark", "inventory_value", "marked_pnl"]]).all()
    assert after["mark"] == 102.0
    assert after["marked_pnl"] == pytest.approx(2.0)


def test_fees_come_out_of_cash():
    mids = _mids((T, 99.0, 101.0))
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.5))

    series = marked_pnl_series(fills, mids, freq="5s")

    assert list(series["cash"]) == pytest.approx([-100.5])
    assert list(series["marked_pnl"]) == pytest.approx([-0.5])


def test_no_fills_gives_a_flat_zero_series_over_the_mids():
    mids = _mids((T, 99.0, 101.0), (T + 5, 109.0, 111.0))

    series = marked_pnl_series(pd.DataFrame(), mids, freq="5s")

    assert list(series["time"]) == [_utc(T), _utc(T + 5)]
    assert list(series["cash"]) == [0.0, 0.0]
    assert list(series["position"]) == [0.0, 0.0]
    assert list(series["mark"]) == pytest.approx([100.0, 110.0])
    assert list(series["marked_pnl"]) == [0.0, 0.0]


def test_no_mids_gives_an_empty_series():
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_series(fills, pd.DataFrame(), freq="5s")

    assert series.empty
    assert list(series.columns) == [
        "time",
        "cash",
        "position",
        "mark",
        "inventory_value",
        "marked_pnl",
    ]


def test_fill_between_bucket_starts_lands_in_the_bucket_it_falls_in():
    mids = _mids((T, 99.0, 101.0), (T + 10, 99.0, 101.0))
    fills = _fills_at((T + 7.5, "BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_series(fills, mids, freq="5s")

    assert list(series["time"]) == [_utc(T), _utc(T + 5), _utc(T + 10)]
    assert list(series["position"]) == [0.0, 1.0, 1.0]


def test_bucket_time_is_the_start_of_the_bucket():
    # 22:13:20 falls in the minute that started at 22:13:00.
    mids = _mids((T, 99.0, 101.0))
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_series(fills, mids, freq="1min")

    assert list(series["time"]) == [_utc(T - 20)]


def test_fills_on_series_take_the_pnl_of_their_bucket():
    mids = _mids(
        (T, 99.0, 101.0), (T + 5, 109.0, 111.0), (T + 10, 119.0, 121.0)
    )
    fills = _fills_at(
        (T + 6, "SELL", 110.0, 1.0, 0.0), (T + 1, "BUY", 100.0, 2.0, 0.0)
    )
    series = marked_pnl_series(fills, mids, freq="5s")

    on_line = fills_on_series(fills, series)

    # In time order, at each fill's own time rather than its bucket's,
    # with the PnL its bucket ended on: 0 and 20, as worked out in
    # test_marked_pnl_series_values_held_inventory_at_the_bucket_mid.
    assert list(on_line["time"]) == [_utc(T + 1), _utc(T + 6)]
    assert list(on_line["side"]) == ["BUY", "SELL"]
    assert list(on_line["marked_pnl"]) == pytest.approx([0.0, 20.0])


def test_fills_on_series_is_empty_without_fills_or_without_a_series():
    fills = _fills_at((T, "BUY", 100.0, 1.0, 0.0))
    series = marked_pnl_series(fills, _mids((T, 99.0, 101.0)), freq="5s")

    assert fills_on_series(pd.DataFrame(), series).empty
    assert fills_on_series(fills, pd.DataFrame()).empty
