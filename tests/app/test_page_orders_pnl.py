import sqlite3

from streamlit.testing.v1 import AppTest


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
    # cash_pnl = -(99.5 * 1.0) - 0.1 = -99.6; inventory marked at mid 100.5
    # -> inventory_value = 1.0 * 100.5 = 100.5; total_pnl = 0.9
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Cash PnL"] == "-99.60"
    assert metrics["Total PnL (mark-to-market)"] == "0.90"
    # by_symbol table, plus recent orders and recent fills tables.
    assert len(at.dataframe) == 3


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
    # No mark price available, so total PnL falls back to cash PnL alone.
    assert metrics["Cash PnL"] == metrics["Total PnL (mark-to-market)"]
