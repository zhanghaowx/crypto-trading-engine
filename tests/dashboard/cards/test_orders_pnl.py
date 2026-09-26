import sqlite3
from unittest import mock

from streamlit.testing.v1 import AppTest

from jolteon.dashboard.cards.orders_pnl import (
    _derive_visible_markouts,
    fills_table,
)
from jolteon.dashboard.data.sqlite import read_table
from jolteon.dashboard.ui.primitives import (
    MISSING,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
)


def _kpis_script():
    from jolteon.dashboard.cards import orders_pnl

    orders_pnl.render_kpis()


def _fills_script():
    from jolteon.dashboard.cards import orders_pnl

    # Header actions render ahead of the card's own body, the same
    # order the page draws them in.
    orders_pnl.render_header_actions()
    orders_pnl.render_fills()


def _kpi_row_html(at) -> str:
    """The KPI row's own markup, without the stylesheet shipped in the
    same block."""
    return at.get("html")[-1].body.split("</style>", 1)[-1]


def test_kpis_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_fills_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_kpis_shows_no_fills_message_when_empty(empty_db_path):
    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == ["No fills yet."]


def test_fills_shows_no_fills_message_when_empty(empty_db_path):
    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == ["No fills yet."]


def test_renders_the_kpi_row(populated_db_path):
    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    # net cash = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl (Marked PnL) = 0.9.
    markup = _kpi_row_html(at)
    assert "Marked PnL" in markup
    assert "+$0.90" in markup
    assert POSITIVE_COLOR in markup
    assert "Traded notional" in markup
    assert "$99.50" in markup
    assert "Fills" in markup
    assert "1 buy / 0 sell" in markup
    assert "Trading fees" in markup
    assert "$0.10" in markup


def test_renders_recent_fills(populated_db_path):
    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
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
    # prices are still NULL this soon after, so their markout renders as
    # the missing-value marker rather than as zero.
    assert "Edge" in markdown_values
    assert ":green[+$0.40]" in markdown_values
    assert "Cash Flow" in markdown_values
    assert ":red[-$99.50]" in markdown_values
    assert "1.000000" in markdown_values
    assert "Inventory Before" not in markdown_values
    assert "Inventory After" not in markdown_values
    assert "Markout +100ms" in markdown_values
    assert MISSING in markdown_values


def test_download_button_present_when_fills_exist(populated_db_path):
    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    assert len(at.download_button) == 1
    button = at.download_button[0]
    assert button.icon == ":material/download:"
    assert "Download every fill as CSV" in button.help


def test_download_button_hidden_when_no_fills(empty_db_path):
    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert len(at.download_button) == 0


def test_fills_table_uses_readable_headers_and_drops_opaque_ids(
    populated_db_path,
):
    fills = read_table(populated_db_path, "decorated_order_fill")

    # The page derives fair prices for the visible page before rendering
    # it; edge and markout are columns of that derivation, not of the
    # recorded fill.
    display = fills_table(_derive_visible_markouts(populated_db_path, fills))

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

    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    # No mark price available, so Marked PnL falls back to net cash alone:
    # -(99.5 * 1.0) - 0.1 fee = -99.60, in the red.
    markup = _kpi_row_html(at)
    assert "-$99.60" in markup
    assert NEGATIVE_COLOR in markup


def test_a_fill_without_a_trade_id_still_gets_a_stable_row_key(tmp_path):
    """Not every recording carries an execution id; the row still needs a
    key of its own, built from what it does have, or a second fill just
    like it would collide with the first rather than getting a row."""
    db_path = str(tmp_path / "no_trade_id.sqlite")
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

    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert "99.50" in [m.value for m in at.markdown]


def _round_trip_db(tmp_path, sell_price: float) -> str:
    """A closed round trip: one lot bought at 100 and sold back at
    `sell_price`, which is what decides whether the Marked PnL tile reads
    as up or down."""
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


def test_marked_pnl_tile_is_green_while_the_round_trips_are_up(tmp_path):
    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = _round_trip_db(tmp_path, 110.0)
    at.run()

    assert not at.exception
    markup = _kpi_row_html(at)
    assert "+$10.00" in markup
    assert POSITIVE_COLOR in markup
    assert NEGATIVE_COLOR not in markup


def test_marked_pnl_tile_is_red_while_the_round_trips_are_down(tmp_path):
    at = AppTest.from_function(_kpis_script)
    at.session_state["db_path"] = _round_trip_db(tmp_path, 90.0)
    at.run()

    assert not at.exception
    markup = _kpi_row_html(at)
    assert "-$10.00" in markup
    assert NEGATIVE_COLOR in markup


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

    from jolteon.dashboard.cards.orders_pnl import realized_pnl_now

    value = realized_pnl_now(
        st.session_state["db_path"], st.session_state.get("scoped_run_id")
    )
    st.write(f"{value:.2f}")


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
    with mock.patch("jolteon.dashboard.data.sqlite._MAX_CACHED_ROWS", 600):
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


def _fills_card_script():
    from jolteon.dashboard.cards import orders_pnl
    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "recent-fills",
                "Recent fills",
                ":material/receipt_long:",
                orders_pnl.render_fills,
                load=orders_pnl.load,
                actions=orders_pnl.render_header_actions,
            )
        ]
    )


def test_fills_card_shares_one_data_load_across_body_and_download(
    populated_db_path,
):
    from jolteon.dashboard.cards import orders_pnl

    at = AppTest.from_function(_fills_card_script)
    at.session_state["db_path"] = populated_db_path
    at.session_state["auto_refresh"] = False
    with (
        mock.patch.object(orders_pnl, "load", wraps=orders_pnl.load) as load,
        mock.patch.object(
            orders_pnl,
            "read_run_table",
            wraps=orders_pnl.read_run_table,
        ) as read,
    ):
        at.run()
        assert not at.exception
        assert not at.error
        assert load.call_count == read.call_count == 1
        assert len(at.get("download_button")) == 1
        at.button(key="card-recent-fills-refresh").click().run()
        assert not at.exception
        assert not at.error
        assert load.call_count == read.call_count == 2


def test_recent_fill_derives_edge_and_markout_from_fair_price_table(tmp_path):
    db_path = str(tmp_path / "derived-recent-fill.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill ("
            "unique_trade_id TEXT PRIMARY KEY, timestamp REAL, "
            "transaction_timestamp REAL, client_order_id TEXT, "
            "exchange_execution_id TEXT, side TEXT, fill_price REAL, "
            "fill_qty REAL, fee REAL, symbol TEXT, fair_price_model TEXT)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "('fill-1', 10.0, 10.0, 'order-1', 'exec-1', 'BUY', "
            "100.0, 1.0, 0.1, 'BTC/USD', 'AdjustedFairPriceModel')"
        )
        conn.execute(
            "CREATE TABLE fair_price ("
            "timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, 'BTC/USD', "
            "'AdjustedFairPriceModel', ?, ?)",
            [
                (9.9, 100.0, 102.0),
                (10.1, 101.0, 103.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    at = AppTest.from_function(_fills_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    # Fair at fill is 101, so the one-BTC fill keeps $1 less its $0.10 fee.
    assert ":green[+$0.90]" in markdown_values
    # The +100ms target is exactly the second observation, mid 102.
    assert ":green[+$2.00]" in markdown_values


def test_realized_pnl_is_scoped_to_the_current_engine_run(tmp_path):
    db_path = str(tmp_path / "runs.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(transaction_timestamp REAL, side TEXT, fill_price REAL, "
            "fill_qty REAL, fee REAL, symbol TEXT, "
            "exchange_execution_id TEXT PRIMARY KEY, run_id TEXT)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, "BUY", 100.0, 1.0, 0.0, "BTC-USD", "a", "run-a"),
                (2, "SELL", 110.0, 1.0, 0.0, "BTC-USD", "b", "run-a"),
                (3, "BUY", 100.0, 1.0, 0.0, "BTC-USD", "c", "run-b"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    at = AppTest.from_function(_realized_script)
    at.session_state["db_path"] = db_path
    at.session_state["scoped_run_id"] = "run-a"
    at.run()
    assert at.markdown[-1].value == "10.00"

    at.session_state["scoped_run_id"] = "run-b"
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "0.00"
