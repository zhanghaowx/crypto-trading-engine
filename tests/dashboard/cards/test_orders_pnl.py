import sqlite3
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from jolteon.dashboard.cards.orders_pnl import (
    _HORIZON_KEY,
    _SHOW_IDS_KEY,
    _base_asset,
    _derive_visible_markouts,
    fills_table,
)
from jolteon.dashboard.data.sqlite import read_table
from jolteon.dashboard.ui.primitives import MISSING


def _script():
    from jolteon.dashboard.cards import orders_pnl

    # The summary row leads the page; the fills card's header actions
    # render ahead of its own body, the same order the page draws them.
    orders_pnl.render_summary()
    orders_pnl.render_header_actions()
    orders_pnl.render()


def _summary_script():
    from jolteon.dashboard.cards import orders_pnl

    orders_pnl.render_summary()


def _fills_only_script():
    """The fills card's body on its own, before its header has drawn."""
    from jolteon.dashboard.cards import orders_pnl

    orders_pnl.render()


def _metrics(at):
    """Every metric's rendered value, by its label. A colored metric
    carries its color in the value's own markdown (`:green[9.90]`)."""
    return {m.label: m.value for m in at.metric}


def _metric_help(at):
    return {m.label: m.help for m in at.metric}


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    # The fills card warns; the summary row above it stays silent rather
    # than say the same thing twice.
    assert len(at.warning) == 1
    assert not at.info


def test_says_quietly_that_there_are_no_fills_yet(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert not at.info
    # Said once, by the fills card: nothing to sum up is not an alert.
    assert [c.value for c in at.caption] == ["No fills yet."]
    assert not at.metric


def test_the_summary_row_draws_nothing_it_cannot_sum_up(
    missing_db_path, empty_db_path
):
    """A row of the page rather than a card on it, so with no recording
    and before the first fill it has no title to explain itself under."""
    for db_path in (missing_db_path, empty_db_path):
        at = AppTest.from_function(_summary_script)
        at.session_state["db_path"] = db_path
        at.run()

        assert not at.exception
        assert not at.warning and not at.caption and not at.metric


def test_renders_pnl_and_recent_fills(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    # net cash = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl = 0.9. Nothing has
    # been sold back, so realized PnL is just the fee paid. The total
    # carries the name Post-trade gives the same figure, with a sign and
    # a currency; its parts go under its help rather than beside it as
    # peers, and the position is counted in the pair's base asset.
    metrics = _metrics(at)
    assert list(metrics) == ["Marked PnL", "Position", "Fills", "Fees"]
    assert metrics["Marked PnL"] == ":green[+$0.90]"
    assert metrics["Position"] == "1.0 BTC"
    assert metrics["Fills"] == "1"
    assert metrics["Fees"] == "$0.10"
    helps = _metric_help(at)
    assert helps["Marked PnL"] == (
        "Cash flow of the run's fills plus inventory valued at the latest "
        "mid. Cash flow -$99.60, inventory +$100.50, realized on closed "
        "round trips -$0.10."
    )
    assert helps["Position"] == (
        "Inventory held, valued at +$100.50 at the latest mid."
    )
    assert helps["Fills"] == "1 buy / 0 sell."
    assert helps["Fees"] == "Trading fees over this session."
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
    # 1.0 is a $0.50 favorable edge, less the $0.10 fee. A second later
    # the mid is 101.0, so the one markout column shown - the default
    # horizon's - carries $1.50.
    assert "Edge" in markdown_values
    assert ":green[+$0.40]" in markdown_values
    assert "Cash Flow" in markdown_values
    assert ":red[-$99.50]" in markdown_values
    assert "1.000000" in markdown_values
    assert "Inventory Before" not in markdown_values
    assert "Inventory After" not in markdown_values
    assert "Markout +1s" in markdown_values
    assert ":green[+$1.50]" in markdown_values
    # One markout column, and no symbol - the context bar names it. The
    # ids wait behind the header's toggle.
    for hidden in ("Markout +100ms", "Markout +5s", "Markout +30s"):
        assert hidden not in markdown_values
    assert "Symbol" not in markdown_values
    assert "BTC-USD" not in markdown_values
    assert "Trade" not in markdown_values


def test_the_horizon_control_chooses_the_markout_column(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()
    at.segmented_control(key=_HORIZON_KEY).set_value("+30s").run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "Markout +30s" in markdown_values
    assert "Markout +1s" not in markdown_values
    # Half a minute has not passed since the fill, so at this horizon its
    # markout is not a figure yet rather than zero.
    assert MISSING in markdown_values


def test_the_ids_toggle_shows_the_trade_and_order_columns(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()
    at.toggle(key=_SHOW_IDS_KEY).set_value(True).run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "Trade" in markdown_values
    assert "2" in markdown_values


def test_the_list_takes_the_defaults_before_the_header_has_drawn(
    populated_db_path,
):
    """The card draws its body before the header its controls sit in, so
    on the first pass they have no value to read yet."""
    at = AppTest.from_function(_fills_only_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "Markout +1s" in markdown_values
    assert "Trade" not in markdown_values


@pytest.mark.parametrize(
    ("symbol", "asset"),
    [("BTC/USD", "BTC"), ("BTC-USD", "BTC"), ("XBTUSD", "")],
)
def test_the_position_is_counted_in_the_pairs_base_asset(symbol, asset):
    assert _base_asset(symbol) == asset


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

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    # No mark price available, so the marked PnL falls back to the cash
    # flow alone, and its parts say so.
    assert _metrics(at)["Marked PnL"] == ":red[-$99.60]"
    assert "inventory +$0.00" in _metric_help(at)["Marked PnL"]


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


def test_the_fill_count_is_the_recordings_not_the_caches(tmp_path):
    """The dashboard keeps only the most recent rows of a long table, so
    a count taken off them would quietly shrink as the session went on.
    Post-trade counts by the recording, and so does this."""
    db_path = _pnl_db(
        tmp_path,
        "many.sqlite",
        [
            (
                i,
                "BUY" if i % 2 else "SELL",
                100.0,
                1.0,
                0.0,
                "BTC-USD",
                f"f{i}",
            )
            for i in range(12)
        ],
    )

    at = AppTest.from_function(_summary_script)
    at.session_state["db_path"] = db_path
    with mock.patch("jolteon.dashboard.data.sqlite._MAX_CACHED_ROWS", 5):
        at.run()

    assert not at.exception
    assert _metrics(at)["Fills"] == "12"
    assert _metric_help(at)["Fills"] == "6 buy / 6 sell."


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


def _orders_card_script():
    from jolteon.dashboard.cards import orders_pnl
    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "recent-fills",
                "Recent fills",
                ":material/receipt_long:",
                orders_pnl.render,
                load=orders_pnl.load,
                actions=orders_pnl.render_header_actions,
            )
        ]
    )


def test_card_shares_one_data_load_across_body_and_download(
    populated_db_path,
):
    from jolteon.dashboard.cards import orders_pnl

    at = AppTest.from_function(_orders_card_script)
    at.session_state["db_path"] = populated_db_path
    at.session_state["auto_refresh"] = False
    with (
        mock.patch.object(orders_pnl, "load", wraps=orders_pnl.load) as load,
        mock.patch.object(
            orders_pnl,
            "read_run_table",
            wraps=orders_pnl.read_run_table,
        ) as read,
        mock.patch.object(
            orders_pnl,
            "realized_pnl_now",
            wraps=orders_pnl.realized_pnl_now,
        ) as realized,
    ):
        at.run()
        assert not at.exception
        assert not at.error
        assert load.call_count == read.call_count == realized.call_count == 1
        assert ":green-badge[BUY]" in [m.value for m in at.markdown]
        assert len(at.get("download_button")) == 1
        at.button(key="card-recent-fills-refresh").click().run()
        assert not at.exception
        assert not at.error
        assert load.call_count == read.call_count == realized.call_count == 2


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

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()
    # The only fair price after the fill sits a tenth of a second on, so
    # that is the horizon to read the list at.
    at.segmented_control(key=_HORIZON_KEY).set_value("+100ms").run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    # Fair at fill is 101, so the one-BTC fill keeps $1 less its $0.10 fee.
    assert ":green[+$0.90]" in markdown_values
    # The +100ms target is exactly the second observation, mid 102.
    assert ":green[+$2.00]" in markdown_values

    # This fill carries both ids, and both come out from behind the toggle.
    at.toggle(key=_SHOW_IDS_KEY).set_value(True).run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "Order" in markdown_values
    assert "order-1" in markdown_values
    assert "exec-1" in markdown_values


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
