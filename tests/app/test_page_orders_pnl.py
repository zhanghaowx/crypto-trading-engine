import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from jolteon.app.app_pages.orders_pnl import realized_pnl


def _script():
    from jolteon.app.app_pages import orders_pnl

    orders_pnl.render()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_no_fills_and_no_orders_messages_when_empty(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == [
        "No fills yet.",
        "No orders placed yet.",
        "No fills yet.",
    ]


def test_renders_pnl_and_recent_orders_and_fills(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    # net cash = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl = 0.9. Nothing has
    # been sold back, so realized PnL is just the fee paid.
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Net cash flow"] == ":red[-99.60]"
    assert metrics["Realized PnL"] == ":red[-0.10]"
    assert metrics["Total PnL"] == ":green[0.90]"
    assert metrics["Inventory value"] == "100.50"
    assert metrics["BTC-USD position"] == "1"
    assert metrics["BTC-USD mark price"] == "100.50"
    # Recent orders and recent fills; the per-symbol PnL breakdown is
    # rendered as metrics rather than a table.
    assert len(at.dataframe) == 2


def test_tables_use_readable_headers_and_drop_opaque_ids(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    orders, fills = (frame.value for frame in at.dataframe)
    assert list(orders.columns) == [
        "Time",
        "Order",
        "Side",
        "Type",
        "Symbol",
        "Price",
        "Quantity",
        "Value",
    ]
    assert list(fills.columns) == [
        "Time",
        "Trade",
        "Order",
        "Side",
        "Symbol",
        "Price",
        "Quantity",
        "Value",
        "Fee",
    ]
    # The venue's opaque UUIDs and the raw recording timestamp are gone.
    assert "maker_order_id" not in fills
    assert "taker_order_id" not in fills
    assert "timestamp" not in orders


def test_marks_inventory_at_zero_without_a_ticker_feed(tmp_path):
    # Fills exist but no ticker_feed data has been recorded yet, so there
    # is no mid price to mark held inventory against.
    db_path = str(tmp_path / "no_ticker_feed.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE order_fill "
        "(timestamp REAL, side TEXT, price REAL, quantity REAL, "
        "fee REAL, symbol TEXT)"
    )
    conn.execute(
        "INSERT INTO order_fill VALUES "
        "(1700000000, 'BUY', 99.5, 1.0, 0.1, 'BTC-USD')"
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    # No mark price available, so total PnL falls back to net cash alone.
    assert metrics["Net cash flow"] == metrics["Total PnL"]


def _fills(*trades) -> pd.DataFrame:
    """A fills table from `(side, price, quantity, fee)` tuples, in the
    order they were traded."""
    return pd.DataFrame(
        [
            {
                "transaction_time": 1700000000 + index,
                "symbol": "BTC-USD",
                "side": side,
                "price": price,
                "quantity": quantity,
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
