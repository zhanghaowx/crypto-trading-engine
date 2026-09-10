def test_dashboard_renders_every_section_on_one_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Health",
        "Market Data",
        "Risk Limits",
        "Orders & PnL",
        "Trade Quality",
        "Errors",
    ]


def test_dashboard_warns_in_every_section_when_db_missing(dashboard):
    at = dashboard.run()

    assert not at.exception
    # One warning per section (health, market data, risk limits, orders &
    # pnl, trade quality, errors) plus two from the settings popover (db
    # path, log db path) - there's no navigation left to hide the others
    # behind.
    assert len(at.warning) == 8


def test_dashboard_settings_popover_holds_the_viewer_settings(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert at.text_input(key="db_path")
    assert at.text_input(key="log_db_path")
    assert at.checkbox(key="auto_refresh")
    assert at.slider(key="refresh_seconds")
    assert at.slider(key="chart_window_minutes")
