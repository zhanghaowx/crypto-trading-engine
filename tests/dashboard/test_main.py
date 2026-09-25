import sqlite3
import time
from pathlib import Path

from jolteon.dashboard.services.health import HEARTBEAT_TIMEOUT_SECONDS
from jolteon.engine.core.storage import paths


def _card_titles(at) -> list[str]:
    """Each card's title. A card is an expander, so that it folds in the
    browser, and its title is that expander's label with the card's own
    icon in front of it."""
    return [e.label.split(": ", 1)[-1] for e in at.expander]


def test_dashboard_renders_every_section_on_one_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert _card_titles(at) == [
        "Orders & PnL",
        "Order book",
        "Risk limits",
        "Trade quality",
        "Fair price signals",
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
    at.switch_page("pages/parameters.py")
    # The tab the settings live on, named the way a link to them names it.
    at.query_params["tab"] = "Dashboard"
    at.run()

    assert not at.exception
    assert at.toggle(key="auto_refresh")
    assert at.slider(key="refresh_seconds")


def test_parameters_page_does_not_render_the_live_sections(dashboard):
    at = dashboard.run()
    at.switch_page("pages/parameters.py").run()

    assert not at.exception
    assert "Order book" not in _card_titles(at)


def test_post_trade_has_a_page_of_its_own(dashboard):
    """Reading a finished run back is a different job from watching the
    one happening now, so it does not crowd the Live page."""
    at = dashboard.run()
    at.switch_page("pages/post_trade.py").run()

    assert not at.exception
    assert "Order book" not in _card_titles(at)


def test_health_has_a_page_of_its_own(dashboard):
    at = dashboard.run()
    at.switch_page("pages/health.py").run()

    assert not at.exception
    assert _card_titles(at) == ["Health", "Errors"]


def test_the_live_page_no_longer_reports_health(dashboard):
    """
    Health belongs to every engine at once, and the Live page reads one
    engine at a time.
    """
    at = dashboard.run()

    assert "Health" not in _card_titles(at)
    assert "Errors" not in _card_titles(at)


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
    at.switch_page("pages/health.py").run()

    assert not at.exception
    assert "**MD**" in [m.value for m in at.markdown]
    assert "connection dropped" in at.status[0].label


def test_the_health_card_carries_no_accent_while_nothing_is_down(
    dashboard, engines
):
    """A healthy card reads as a plain white surface; only a component
    that has actually gone down earns the card an edge color."""
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])
    dashboard.session_state["root"] = engines.root

    at = dashboard.run()
    at.switch_page("pages/health.py").run()

    assert not at.exception
    rules = " ".join(h.body for h in at.get("html"))
    assert "st-key-card-health {" not in rules


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
                "CREATE TABLE bbo_feed "
                "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
            )
            conn.execute(
                "INSERT INTO bbo_feed VALUES (1, 'BTC/USD', 100, 101)"
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

    at.switch_page("pages/parameters.py").run()
    at.switch_page("pages/live.py").run()

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


def _record_open_run(recording: str, started_at: float) -> None:
    conn = sqlite3.connect(recording)
    try:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES "
            "('20260920T120000Z-deadbeef', 'Kraken', 'BTC/USD', ?, NULL)",
            (started_at,),
        )
        conn.commit()
    finally:
        conn.close()


def test_live_page_shows_the_latest_engine_run(dashboard, engines):
    now = time.time()
    recording = engines.add(
        "BTC/USD", heartbeats=[(now, "MarketMaking", 1, "All good")]
    )
    _record_open_run(recording, started_at=now - 3600)

    dashboard.session_state["root"] = engines.root
    at = dashboard.run()

    assert not at.exception
    assert at.session_state["engine_run"].run_id == "20260920T120000Z-deadbeef"
    assert any("Run `deadbeef`" in caption.value for caption in at.caption)
    assert any(
        ":green-badge[Running]" in m.value
        for m in at.markdown
        if "-badge[" in m.value
    )


def test_live_page_calls_a_run_whose_engine_went_quiet_interrupted(
    dashboard, engines
):
    stale = time.time() - (HEARTBEAT_TIMEOUT_SECONDS + 1)
    recording = engines.add(
        "BTC/USD", heartbeats=[(stale, "MarketMaking", 1, "All good")]
    )
    _record_open_run(recording, started_at=stale - 3600)

    dashboard.session_state["root"] = engines.root
    at = dashboard.run()

    assert not at.exception
    assert any("Run `deadbeef`" in caption.value for caption in at.caption)
    assert any(
        ":orange-badge[Interrupted]" in m.value
        for m in at.markdown
        if "-badge[" in m.value
    )
