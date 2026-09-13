def test_dashboard_renders_every_section_on_one_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Health",
        "Market Data",
        "Risk Limits",
        "Orders & PnL",
        "Trade Quality",
        "Fair Price Signals",
        "Errors",
    ]


def test_dashboard_hides_errors_section_once_confirmed_empty(
    dashboard, empty_db_path
):
    dashboard.session_state["log_db_path"] = empty_db_path
    at = dashboard.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Health",
        "Market Data",
        "Risk Limits",
        "Orders & PnL",
        "Trade Quality",
        "Fair Price Signals",
    ]


def test_dashboard_warns_in_every_section_when_db_missing(dashboard):
    at = dashboard.run()

    assert not at.exception
    # One warning per section: health, market data, risk limits, orders &
    # pnl, trade quality, fair price signals, errors. The viewer settings
    # that used to warn here alongside them are on the Parameters page now.
    assert len(at.warning) == 7


def test_dashboard_opens_on_the_live_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    # The viewer settings live on the other page, so nothing here binds
    # them - reaching them has to go through navigation.
    assert not at.text_input


def test_parameters_page_holds_the_viewer_settings(dashboard):
    at = dashboard.run()
    at.switch_page("app_pages/parameters.py").run()

    assert not at.exception
    assert at.toggle(key="auto_refresh")
    assert at.slider(key="refresh_seconds")
    assert at.slider(key="chart_window_minutes")


def test_parameters_page_does_not_render_the_live_sections(dashboard):
    at = dashboard.run()
    at.switch_page("app_pages/parameters.py").run()

    assert not at.exception
    assert "Health" not in [s.value for s in at.subheader]


def test_offers_no_symbol_to_choose_while_one_engine_is_running(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert len(at.segmented_control) == 0


def test_offers_every_symbol_being_traded(dashboard, tmp_path, recordings):
    dashboard.session_state["root"] = str(tmp_path)
    at = dashboard.run()

    assert not at.exception
    assert ["BTC/USD", "ETH/USD"] == at.segmented_control[0].options


def test_reads_the_first_engine_until_another_is_chosen(
    dashboard, tmp_path, recordings
):
    dashboard.session_state["root"] = str(tmp_path)
    del dashboard.session_state["db_path"]
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
    at.segmented_control[0].set_value("ETH/USD").run()

    assert not at.exception
    assert at.session_state["db_path"] == recordings["ETH/USD"]
    assert at.session_state["log_db_path"].endswith("ETH-USD/live.log.sqlite")
