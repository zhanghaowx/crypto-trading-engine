def test_dashboard_renders_every_section_on_one_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Market Data",
        "Risk Limits",
        "Orders & PnL",
        "Health",
    ]


def test_dashboard_warns_in_every_section_when_db_missing(dashboard):
    at = dashboard.run()

    assert not at.exception
    # One warning per section (market data, risk limits, orders & pnl,
    # health) plus one from the settings popover - there's no navigation
    # left to hide the others behind.
    assert len(at.warning) == 5


def test_dashboard_settings_popover_holds_the_viewer_settings(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert at.text_input(key="db_path")
    assert at.checkbox(key="auto_refresh")
    assert at.slider(key="refresh_seconds")
