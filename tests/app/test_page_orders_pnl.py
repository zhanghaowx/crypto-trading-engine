import sqlite3
from unittest import mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from jolteon.app.app_pages.orders_pnl import fills_table, realized_pnl
from jolteon.app.data import read_table


def _script():
    from jolteon.app.app_pages import orders_pnl

    # Mirrors dashboard.py's `_section`, which renders each card - header
    # actions ahead of a card's own body, then every card in order - since
    # Orders & PnL and Trade Quality are separate cards on the same page.
    orders_pnl.render_header_actions()
    orders_pnl.render()
    orders_pnl.render_trade_quality()


def _metrics(at):
    """Every metric's rendered value, by its label. A colored metric
    carries its color in the value's own markdown (`:green[9.90]`)."""
    return {m.label: m.value for m in at.metric}


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
    assert [i.value for i in at.info] == [
        "No fills yet.",
        "No fills yet.",
        "No fills yet.",
    ]


def test_renders_pnl_and_recent_fills(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    # net cash = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl = 0.9. Nothing has
    # been sold back, so realized PnL is just the fee paid.
    metrics = _metrics(at)
    assert metrics["Net cash flow"] == ":red[-99.60]"
    assert metrics["Realized PnL"] == ":red[-0.10]"
    assert metrics["Total PnL"] == ":green[0.90]"
    assert metrics["Inventory value"] == "100.50"
    assert metrics["BTC-USD position"] == "1.0"
    # Recent fills renders as a row list, not st.dataframe (a canvas-drawn
    # grid, whose cells can't be styled per side) - check for the header
    # and the one fill's own values instead of a dataframe.
    markdown_values = [m.value for m in at.markdown]
    assert "Time" in markdown_values
    assert "Side" in markdown_values
    assert ":green-badge[BUY]" in markdown_values
    assert "99.50" in markdown_values
    # PostTradeService's fields drive derived edge/markout, not the raw
    # fair prices: fair_price_at_fill=100.0 vs fill_price=99.5 on a BUY of
    # 1.0 is a $0.50 favorable edge, less the $0.10 fee; the horizon fair
    # prices are still NULL this soon after, so their markout renders "-".
    assert "Edge" in markdown_values
    assert ":green[+$0.40]" in markdown_values
    assert "Cash Flow" in markdown_values
    assert ":red[-$99.50]" in markdown_values
    assert "1.000000" in markdown_values
    assert "Inventory Before" not in markdown_values
    assert "Inventory After" not in markdown_values
    assert "Markout +100ms" in markdown_values
    assert "-" in markdown_values


def test_download_button_present_when_fills_exist(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    assert len(at.download_button) == 1
    button = at.download_button[0]
    assert button.icon == ":material/download:"
    assert "Download every fill as CSV" in button.help


def test_download_button_hidden_when_no_fills(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert len(at.download_button) == 0


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
        "Edge",
        "Quantity",
        "Cash Flow",
        "Fee",
        "Markout +100ms",
        "Markout +1s",
        "Markout +5s",
        "Markout +30s",
    ]
    # The venue's opaque UUIDs are gone.
    assert "maker_order_id" not in display
    assert "taker_order_id" not in display


def test_renders_fill_quality_by_side_and_fair_price_movement(
    tmp_path, tables, table_lookup
):
    db_path = str(tmp_path / "fill_quality.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE decorated_order_fill "
        "(timestamp REAL, transaction_timestamp REAL, side TEXT, "
        "fill_price REAL, fill_qty REAL, fee REAL, symbol TEXT, "
        "exchange_execution_id TEXT PRIMARY KEY, fair_price_at_fill REAL, "
        "inventory_before REAL, inventory_after REAL, "
        "fair_price_100ms REAL, fair_price_1s REAL, fair_price_5s REAL, "
        "fair_price_30s REAL)"
    )
    rows = [
        # BUY favorable then adverse, averaging to a $0 edge and markout.
        (
            1700000000,
            1700000000,
            "BUY",
            100.0,
            1.0,
            0.1,
            "BTC-USD",
            1,
            101.0,
            0.0,
            1.0,
            102.0,
            None,
            None,
            None,
        ),
        (
            1700000001,
            1700000001,
            "BUY",
            100.0,
            1.0,
            0.2,
            "BTC-USD",
            2,
            99.0,
            1.0,
            2.0,
            98.0,
            None,
            None,
            None,
        ),
        # SELL, favorable on both edge and markout.
        (
            1700000002,
            1700000002,
            "SELL",
            110.0,
            1.0,
            0.05,
            "BTC-USD",
            3,
            108.0,
            2.0,
            1.0,
            105.0,
            None,
            None,
            None,
        ),
    ]
    conn.executemany(
        "INSERT INTO decorated_order_fill VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Fill Quality**" in markdown_values
    assert "**Fair price movement**" in markdown_values

    fill_quality = table_lookup(at, 0, "Side")
    assert fill_quality["BUY"]["Fills"] == "2"
    assert fill_quality["BUY"]["Average edge"] == "+$0.00"
    assert fill_quality["BUY"]["Markout +100ms"] == "+$0.00"
    assert fill_quality["SELL"]["Fills"] == "1"
    assert fill_quality["SELL"]["Average edge"] == "+$2.00"
    assert fill_quality["SELL"]["Markout +100ms"] == "+$5.00"
    # No fill has a 1s/5s/30s fair price backfilled yet.
    assert fill_quality["BUY"]["Markout +1s"] == "–"

    # Fair price movement is side-independent: (102-101) + (98-99) +
    # (105-108) averaged across all three fills = -1. It's the third
    # table on the page - fill quality, then inventory buckets (this
    # schema has inventory_before too), then this one.
    movement = tables(at)[2]
    row = dict(zip(movement["columns"], movement["rows"][0]))
    assert row["+100ms"] == "-$1.00"
    assert row["+1s"] == "–"


def test_renders_inventory_buckets(tmp_path, table_lookup):
    db_path = str(tmp_path / "inventory_buckets.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE decorated_order_fill "
        "(timestamp REAL, transaction_timestamp REAL, side TEXT, "
        "fill_price REAL, fill_qty REAL, fee REAL, symbol TEXT, "
        "exchange_execution_id TEXT PRIMARY KEY, fair_price_at_fill REAL, "
        "inventory_before REAL, inventory_after REAL, "
        "fair_price_100ms REAL, fair_price_1s REAL, fair_price_5s REAL, "
        "fair_price_30s REAL)"
    )
    rows = [
        # Strongly short: one BUY.
        (
            1700000000,
            1700000000,
            "BUY",
            100.0,
            1.0,
            0.1,
            "BTC-USD",
            1,
            100.0,
            -0.6,
            -0.5,
            103.0,
            None,
            None,
            None,
        ),
        # Near neutral: one SELL.
        (
            1700000001,
            1700000001,
            "SELL",
            100.0,
            1.0,
            0.2,
            "BTC-USD",
            2,
            100.0,
            0.0,
            -1.0,
            98.0,
            None,
            None,
            None,
        ),
    ]
    conn.executemany(
        "INSERT INTO decorated_order_fill VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Inventory Buckets**" in markdown_values

    # Fill quality (BUY/SELL, one each) is the first table on the page;
    # inventory buckets is the second.
    buckets = table_lookup(at, 1, "Inventory")
    assert "Strongly short" in buckets
    assert "Near neutral" in buckets
    assert "Strongly long" not in buckets

    assert buckets["Strongly short"]["Fills"] == "1"
    assert buckets["Strongly short"]["BUY"] == "1"
    assert buckets["Strongly short"]["SELL"] == "0"
    assert buckets["Strongly short"]["Markout +100ms"] == "+$3.00"
    assert buckets["Near neutral"]["Fills"] == "1"
    assert buckets["Near neutral"]["Markout +100ms"] == "+$2.00"


def test_a_fill_without_the_position_held_before_it_joins_no_bucket(tmp_path):
    """A bucket says how we traded while holding that much, so a fill
    recorded without the position held before it belongs to none of them
    - rather than falling through every bound into the extreme one."""
    from jolteon.app import aggregates

    db_path = str(tmp_path / "unset.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(side TEXT, fill_price REAL, fair_price_at_fill REAL, "
            "fill_qty REAL, fee REAL, inventory_before REAL, "
            "fair_price_100ms REAL, fair_price_1s REAL, "
            "fair_price_5s REAL, fair_price_30s REAL)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "('BUY', 100.0, 100.0, 1.0, 0.1, NULL, NULL, NULL, NULL, NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    assert aggregates.inventory_buckets(db_path).empty


def test_marks_inventory_at_zero_without_a_bbo_feed(tmp_path):
    # Fills exist but no bbo_feed data has been recorded yet, so there
    # is no mid price to mark held inventory against.
    db_path = str(tmp_path / "no_bbo_feed.sqlite")
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
    metrics = _metrics(at)
    # No mark price available, so total PnL falls back to net cash alone.
    assert metrics["Net cash flow"] == metrics["Total PnL"]
    assert "BTC-USD mark price" not in metrics


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


def _accent_script():
    import streamlit as st

    from jolteon.app.app_pages import orders_pnl

    st.write(str(orders_pnl.accent()))


def _round_trip_db(tmp_path, sell_price: float) -> str:
    """A closed round trip: one lot bought at 100 and sold back at
    `sell_price`, which is what decides whether the card reads as up or
    down."""
    db_path = str(tmp_path / f"round-trip-{sell_price}.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, transaction_timestamp REAL, side TEXT, "
            "fill_price REAL, fill_qty REAL, fee REAL, symbol TEXT, "
            "exchange_execution_id TEXT PRIMARY KEY, fair_price_at_fill REAL, "
            "inventory_before REAL, inventory_after REAL, "
            "fair_price_100ms REAL, fair_price_1s REAL, fair_price_5s REAL, "
            "fair_price_30s REAL)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES "
            "(?, ?, ?, ?, 1.0, 0.0, 'BTC-USD', ?, 100.0, 0.0, 0.0, "
            "NULL, NULL, NULL, NULL)",
            [
                (1700000000, 1700000000, "BUY", 100.0, 1),
                (1700000001, 1700000001, "SELL", sell_price, 2),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_accent_is_absent_before_the_first_fill(empty_db_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "None"


def test_accent_is_green_while_the_round_trips_are_up(tmp_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = _round_trip_db(tmp_path, 110.0)
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "green"


def test_accent_is_red_while_the_round_trips_are_down(tmp_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = _round_trip_db(tmp_path, 90.0)
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "red"


def _pnl_db(tmp_path, name, fills) -> str:
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(transaction_timestamp REAL, side TEXT, fill_price REAL, "
            "fill_qty REAL, fee REAL, symbol TEXT, "
            "exchange_execution_id TEXT PRIMARY KEY)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?,?,?,?,?,?,?)", fills
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _add_fills(db_path, fills) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?,?,?,?,?,?,?)", fills
        )
        conn.commit()
    finally:
        conn.close()


def _realized_script():
    import streamlit as st

    from jolteon.app.app_pages.orders_pnl import realized_pnl_now

    st.write(f"{realized_pnl_now(st.session_state['db_path']):.2f}")


def test_realized_pnl_carries_over_and_takes_only_the_new_fills(tmp_path):
    """A round trip closed across two refreshes has to be counted once,
    by a refresh that only ever sees the second half of it."""
    db_path = _pnl_db(
        tmp_path,
        "carry.sqlite",
        [(1, "BUY", 100.0, 1.0, 0.0, "BTC-USD", "a")],
    )

    at = AppTest.from_function(_realized_script)
    at.session_state["db_path"] = db_path
    at.run()
    # Bought and still holding: nothing has been realized.
    assert at.markdown[-1].value == "0.00"

    _add_fills(db_path, [(2, "SELL", 110.0, 1.0, 0.0, "BTC-USD", "b")])
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "10.00"


def test_realized_pnl_survives_a_table_longer_than_the_cache(tmp_path):
    """
    Regression test: realized PnL was walked over whatever the table
    cache happened to be holding, which is the most recent rows only. The
    fills that opened the position are the oldest of all, so once the
    session outgrew the cache the walk started from the middle and the
    figure was quietly wrong - 1000.00 against a true 5000.00 when this
    was written.
    """
    opened = [
        (i, "BUY", 100.0, 1.0, 0.0, "BTC-USD", f"b{i}") for i in range(500)
    ]
    closed = [
        (500 + i, "SELL", 110.0, 1.0, 0.0, "BTC-USD", f"s{i}")
        for i in range(500)
    ]
    db_path = _pnl_db(tmp_path, "long.sqlite", opened + closed)

    at = AppTest.from_function(_realized_script)
    at.session_state["db_path"] = db_path
    with mock.patch("jolteon.app.data._MAX_CACHED_ROWS", 600):
        at.run()

    assert not at.exception
    assert at.markdown[-1].value == "5000.00"


def test_realized_pnl_starts_again_for_another_engines_recording(tmp_path):
    """The round trips closed under one engine say nothing about
    another's."""
    first = _pnl_db(
        tmp_path,
        "btc.sqlite",
        [
            (1, "BUY", 100.0, 1.0, 0.0, "BTC-USD", "a"),
            (2, "SELL", 110.0, 1.0, 0.0, "BTC-USD", "b"),
        ],
    )
    second = _pnl_db(
        tmp_path, "eth.sqlite", [(1, "BUY", 50.0, 1.0, 0.0, "ETH-USD", "a")]
    )

    at = AppTest.from_function(_realized_script)
    at.session_state["db_path"] = first
    at.run()
    assert at.markdown[-1].value == "10.00"

    at.session_state["db_path"] = second
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "0.00"


def test_realized_pnl_starts_again_when_the_recording_is_replaced(tmp_path):
    """Row ids start over when a recording is replaced, and the round
    trips carried from the old one never happened in the new."""
    db_path = _pnl_db(
        tmp_path,
        "replaced.sqlite",
        [
            (1, "BUY", 100.0, 1.0, 0.0, "BTC-USD", "a"),
            (2, "SELL", 110.0, 1.0, 0.0, "BTC-USD", "b"),
        ],
    )

    at = AppTest.from_function(_realized_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "10.00"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM decorated_order_fill")
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "(1, 'BUY', 100.0, 1.0, 0.0, 'BTC-USD', 'z')"
        )
        conn.commit()
    finally:
        conn.close()
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "0.00"
