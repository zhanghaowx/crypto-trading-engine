import json
import sqlite3

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import market_data

    market_data.render()


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


def test_shows_info_when_no_market_data_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No market data recorded yet."


def test_renders_metrics_and_chart_from_recorded_data(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.session_state["chart_window_minutes"] = 15
    at.run()

    assert not at.exception
    assert at.metric[0].label == "Symbol"
    assert at.metric[0].value == "BTC-USD"

    metrics = _animated_metrics(at)
    assert metrics["bid"]["value"] == 100.0
    assert metrics["ask"]["value"] == 101.0
    assert metrics["mid"]["value"] == 100.5
    # Buy/Sell Quote are colored green/red to match the quote lines drawn
    # on the price chart.
    assert metrics["quote-BUY"]["value"] == 99.5
    assert metrics["quote-BUY"]["color"] == "#4E9F1F"
    assert "quote-SELL" not in metrics
    assert {m.label: m.value for m in at.metric}["Sell Quote"] == "—"
    assert len(at.get("vega_lite_chart")) == 1


def test_sell_quote_is_colored_red(tmp_path):
    db_path = str(tmp_path / "both_sides.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE ticker_feed "
        "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
    )
    conn.execute(
        "INSERT INTO ticker_feed VALUES (1700000000, 'BTC-USD', 100.0, 101.0)"
    )
    conn.execute(
        'CREATE TABLE "order" '
        "(timestamp REAL, side TEXT, price REAL, symbol TEXT, "
        "client_order_id TEXT)"
    )
    conn.executemany(
        'INSERT INTO "order" VALUES (?, ?, ?, ?, ?)',
        [
            (1700000000, "BUY", 99.5, "BTC-USD", "1"),
            (1700000000, "SELL", 101.5, "BTC-USD", "2"),
        ],
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.session_state["chart_window_minutes"] = 15
    at.run()

    assert not at.exception
    metrics = _animated_metrics(at)
    assert metrics["quote-BUY"]["value"] == 99.5
    assert metrics["quote-BUY"]["color"] == "#4E9F1F"
    assert metrics["quote-SELL"]["value"] == 101.5
    assert metrics["quote-SELL"]["color"] == "#E2574C"
