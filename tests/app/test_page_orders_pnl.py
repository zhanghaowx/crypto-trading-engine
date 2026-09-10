import json
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from jolteon.app.app_pages.orders_pnl import fills_table, realized_pnl
from jolteon.app.data import read_table


def _script():
    from jolteon.app.app_pages import orders_pnl

    orders_pnl.render()


def _animated_metrics(at):
    """Args passed to each `animated_metric` custom component, by its key.

    `st.metric` values are exposed by AppTest directly (`at.metric`), but a
    custom component is not - it only shows up as a generic
    `component_instance`, whose `json_args` carries what was passed in.
    """
    return {
        e.key: json.loads(e.json_args) for e in at.get("component_instance")
    }


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_no_fills_messages_when_empty(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == ["No fills yet.", "No fills yet."]


def test_renders_pnl_and_recent_fills(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    # net cash = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl = 0.9. Nothing has
    # been sold back, so realized PnL is just the fee paid.
    metrics = _animated_metrics(at)
    assert metrics["net-cash-flow"]["value"] == pytest.approx(-99.6)
    assert metrics["net-cash-flow"]["color"] == "#E2574C"
    assert metrics["realized-pnl"]["value"] == pytest.approx(-0.1)
    assert metrics["realized-pnl"]["color"] == "#E2574C"
    assert metrics["total-pnl"]["value"] == pytest.approx(0.9)
    assert metrics["total-pnl"]["color"] == "#4E9F1F"
    assert metrics["inventory-value"]["value"] == pytest.approx(100.5)
    assert metrics["BTC-USD-position"]["value"] == 1.0
    assert metrics["BTC-USD-mark-price"]["value"] == pytest.approx(100.5)
    # Recent fills renders as a row list, not st.dataframe (a canvas-drawn
    # grid, which can't play a per-row entrance animation) - check for the
    # header and the one fill's own values instead of a dataframe.
    markdown_values = [m.value for m in at.markdown]
    assert "**Time**" in markdown_values
    assert "**Side**" in markdown_values
    assert ":green-badge[BUY]" in markdown_values
    assert "99.50" in markdown_values


def test_fills_table_uses_readable_headers_and_drops_opaque_ids(
    populated_db_path,
):
    fills = read_table(populated_db_path, "decorated_order_fill")

    display = fills_table(fills)

    # decorated_order_fill carries no client_order_id, so "Order" isn't
    # rendered - `_optional` drops whatever column the table doesn't have.
    assert list(display.columns) == [
        "Time",
        "Trade",
        "Side",
        "Symbol",
        "Price",
        "Quantity",
        "Value",
        "Fee",
    ]
    # The venue's opaque UUIDs are gone.
    assert "maker_order_id" not in display
    assert "taker_order_id" not in display


def test_marks_inventory_at_zero_without_a_ticker_feed(tmp_path):
    # Fills exist but no ticker_feed data has been recorded yet, so there
    # is no mid price to mark held inventory against.
    db_path = str(tmp_path / "no_ticker_feed.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE decorated_order_fill "
        "(timestamp REAL, side TEXT, fill_price REAL, fill_qty REAL, "
        "fee REAL, symbol TEXT)"
    )
    conn.execute(
        "INSERT INTO decorated_order_fill VALUES "
        "(1700000000, 'BUY', 99.5, 1.0, 0.1, 'BTC-USD')"
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    metrics = _animated_metrics(at)
    # No mark price available, so total PnL falls back to net cash alone.
    assert metrics["net-cash-flow"]["value"] == metrics["total-pnl"]["value"]
    # And the mark price itself falls back to a plain, unanimated "-".
    assert {m.label: m.value for m in at.metric}["BTC-USD mark price"] == "-"


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
