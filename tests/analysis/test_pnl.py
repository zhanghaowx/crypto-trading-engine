import pandas as pd
import pytest

from jolteon.analysis.pnl import (
    marked_pnl_over_time,
    realized_pnl,
    signed_cash_flow,
    traded_notional,
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


def test_traded_notional_sums_price_times_quantity_over_every_fill():
    fills = _fills(("BUY", 100.0, 1.0, 0.0), ("SELL", 110.0, 2.0, 0.0))
    assert traded_notional(fills) == pytest.approx(320.0)


def test_traded_notional_is_zero_with_no_fills():
    assert traded_notional(pd.DataFrame()) == 0.0


def _mids(*points) -> pd.DataFrame:
    """A mid-price series from `(timestamp, mid_price)` tuples."""
    return pd.DataFrame(points, columns=["timestamp", "mid_price"])


def test_marked_pnl_is_flat_zero_before_any_fill():
    fills = _fills(("BUY", 100.0, 1.0, 1.0))
    mids = _mids((1700000000 - 10, 90.0))

    series = marked_pnl_over_time(fills, mids)

    assert list(series["marked_pnl"]) == pytest.approx([0.0])


def test_marked_pnl_moves_with_the_mid_after_a_fill():
    # Buys one unit at 100, paying a $1 fee: net cash is -101. Marked to a
    # later mid of 110, the unit held is worth 110, for a marked PnL of 9.
    fills = _fills(("BUY", 100.0, 1.0, 1.0))
    mids = _mids((1700000000 + 10, 110.0))

    series = marked_pnl_over_time(fills, mids)

    assert list(series["timestamp"]) == [1700000000 + 10]
    assert list(series["marked_pnl"]) == pytest.approx([9.0])


def test_marked_pnl_carries_the_position_forward_between_mid_prices():
    fills = _fills(("BUY", 100.0, 1.0, 0.0))
    mids = _mids(
        (1700000000 - 5, 95.0),
        (1700000000 + 5, 105.0),
        (1700000000 + 15, 120.0),
    )

    series = marked_pnl_over_time(fills, mids)

    assert list(series["marked_pnl"]) == pytest.approx([0.0, 5.0, 20.0])


def test_marked_pnl_is_zero_throughout_with_no_fills():
    mids = _mids((1, 100.0), (2, 105.0))

    series = marked_pnl_over_time(pd.DataFrame(), mids)

    assert list(series["marked_pnl"]) == pytest.approx([0.0, 0.0])


def test_marked_pnl_is_empty_with_no_mid_prices():
    fills = _fills(("BUY", 100.0, 1.0, 0.0))

    series = marked_pnl_over_time(
        fills, pd.DataFrame(columns=["timestamp", "mid_price"])
    )

    assert list(series.columns) == ["timestamp", "marked_pnl"]
    assert series.empty
