def test_dashboard_defaults_to_market_data_page(dashboard):
    at = dashboard.run()

    assert not at.exception
    assert at.title[0].value == "Market Data"


def test_dashboard_navigates_to_every_page(dashboard, populated_db_path):
    dashboard.session_state["db_path"] = populated_db_path
    at = dashboard.run()

    for page, title in [
        ("app_pages/risk_limits.py", "Risk Limits"),
        ("app_pages/orders_pnl.py", "Orders & PnL"),
        ("app_pages/health.py", "Health"),
        ("app_pages/parameters.py", "Parameters"),
    ]:
        at.switch_page(page).run()
        assert not at.exception, f"{page} raised: {at.exception}"
        assert at.title[0].value == title
