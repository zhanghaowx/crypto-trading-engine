import sqlite3
import time
from pathlib import Path

from jolteon.engine.core.storage import paths


def test_dashboard_renders_every_section_on_one_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Market Data",
        "Risk Limits",
        "Orders & PnL",
        "Trade Quality",
        "Fair Price Signals",
    ]


def test_dashboard_warns_in_every_section_when_db_missing(dashboard):
    at = dashboard.run()

    assert not at.exception
    # One warning per section: market data, risk limits, orders & pnl,
    # trade quality, fair price signals. Health and errors are on a page
    # of their own, and the viewer settings on the Parameters page.
    assert len(at.warning) == 5


def test_dashboard_opens_on_the_live_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    # The viewer settings live on the other page, so nothing here binds
    # them - reaching them has to go through navigation.
    assert not at.text_input


def test_parameters_page_holds_the_viewer_settings(dashboard):
    at = dashboard.run()
    at.switch_page("app_pages/parameters.py")
    # The tab the settings live on, named the way a link to them names it.
    at.query_params["tab"] = "Dashboard"
    at.run()

    assert not at.exception
    assert at.toggle(key="auto_refresh")
    assert at.slider(key="refresh_seconds")
    assert at.slider(key="chart_window_minutes")


def test_parameters_page_does_not_render_the_live_sections(dashboard):
    at = dashboard.run()
    at.switch_page("app_pages/parameters.py").run()

    assert not at.exception
    assert "Market Data" not in [s.value for s in at.subheader]


def test_health_has_a_page_of_its_own(dashboard):
    at = dashboard.run()
    at.switch_page("app_pages/health.py").run()

    assert not at.exception
    assert [s.value for s in at.subheader] == ["Health", "Errors"]


def test_the_live_page_no_longer_reports_health(dashboard):
    """
    Health belongs to every engine at once, and the Live page reads one
    engine at a time.
    """
    at = dashboard.run()

    assert "Health" not in [s.value for s in at.subheader]
    assert "Errors" not in [s.value for s in at.subheader]


def test_the_health_page_watches_every_engine(dashboard, engines):
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])
    engines.add(
        "ETH/USD",
        logs=[
            (
                "1700000000.0",
                "jolteon",
                "ERROR",
                "feed.py",
                "42",
                "connection dropped",
            )
        ],
    )
    dashboard.session_state["root"] = engines.root

    at = dashboard.run()
    at.switch_page("app_pages/health.py").run()

    assert not at.exception
    assert "**MD**" in [m.value for m in at.markdown]
    assert "connection dropped" in at.status[0].label


def test_offers_no_symbol_to_choose_while_one_engine_is_running(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert len(at.segmented_control) == 0


def test_offers_every_symbol_being_traded(dashboard, tmp_path, recordings):
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()

    assert not at.exception
    assert ["Kraken · BTC/USD", "Kraken · ETH/USD"] == at.segmented_control[
        0
    ].options


def test_selects_same_symbol_on_two_exchanges(dashboard, tmp_path):
    recordings = {}
    for exchange in ("Kraken", "Binance.US"):
        path = paths.recording(str(tmp_path), exchange, "BTC/USD")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE ticker_feed "
                "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
            )
            conn.execute(
                "INSERT INTO ticker_feed VALUES (1, 'BTC/USD', 100, 101)"
            )
            conn.commit()
        finally:
            conn.close()
        recordings[exchange] = path

    dashboard.session_state["root"] = str(tmp_path)
    del dashboard.session_state["params_db_path"]
    at = dashboard.run()

    assert at.segmented_control[0].options == [
        "Binance.US · BTC/USD",
        "Kraken · BTC/USD",
    ]
    at.segmented_control[0].set_value("kraken:BTC/USD").run()
    assert at.session_state["db_path"] == recordings["Kraken"]
    assert at.session_state["params_db_path"] == paths.parameter_store(
        str(tmp_path), "Kraken"
    )

    at.segmented_control[0].set_value("binance-us:BTC/USD").run()
    assert at.session_state["db_path"] == recordings["Binance.US"]
    assert at.session_state["params_db_path"] == paths.parameter_store(
        str(tmp_path), "Binance.US"
    )


def test_reads_the_first_engine_until_another_is_chosen(
    dashboard, tmp_path, recordings
):
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()

    assert not at.exception
    assert at.session_state["db_path"] == recordings["BTC/USD"]


def test_choosing_a_symbol_reads_that_engines_recording(
    dashboard, tmp_path, recordings
):
    """
    One engine records to one file, so picking a symbol has to repoint
    every section at that engine's database and its logs.
    """
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()
    at.segmented_control[0].set_value("kraken:ETH/USD").run()

    assert not at.exception
    assert at.session_state["db_path"] == recordings["ETH/USD"]
    assert at.session_state["log_db_path"] == paths.log_database(
        str(tmp_path), "ETH/USD"
    )


def test_the_symbol_survives_a_page_switch(dashboard, tmp_path, recordings):
    """
    A widget's value is dropped while the widget is not rendered, and the
    picker is drawn on the Live page alone - so leaving the page and
    coming back used to hand the reader the first engine again, with the
    picker showing it as though they had chosen it.
    """
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()
    at.segmented_control[0].set_value("kraken:ETH/USD").run()

    at.switch_page("app_pages/parameters.py").run()
    at.switch_page("app_pages/live.py").run()

    assert not at.exception
    assert at.session_state["db_path"] == recordings["ETH/USD"]
    assert at.segmented_control[0].value == "kraken:ETH/USD"


def test_the_symbol_a_link_names_is_the_symbol_it_opens_on(
    dashboard, tmp_path, recordings
):
    dashboard.session_state["root"] = str(tmp_path)
    dashboard.query_params["engine"] = "kraken:ETH/USD"
    at = dashboard.run()

    assert not at.exception
    assert at.session_state["db_path"] == recordings["ETH/USD"]


def test_the_reader_cannot_choose_no_symbol_at_all(
    dashboard, tmp_path, recordings
):
    """
    Cleared, every section would go on reading the engine the reader had
    just stopped asking for.
    """
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()

    assert at.segmented_control[0].proto.required
