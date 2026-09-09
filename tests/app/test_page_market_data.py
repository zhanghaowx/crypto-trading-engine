def test_shows_warning_when_db_missing(dashboard):
    # Market Data is the dashboard's default page, so a plain run already
    # lands here.
    at = dashboard.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_market_data_recorded(dashboard, empty_db_path):
    dashboard.session_state["db_path"] = empty_db_path
    at = dashboard.run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No market data recorded yet."


def test_renders_metrics_and_chart_from_recorded_data(
    dashboard, populated_db_path
):
    dashboard.session_state["db_path"] = populated_db_path
    at = dashboard.run()

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Symbol"] == "BTC-USD"
    assert metrics["Bid"] == "100.00"
    assert metrics["Ask"] == "101.00"
    assert metrics["Mid"] == "100.50"
    assert metrics["Buy Quote"] == "99.50"
    assert metrics["Sell Quote"] == "—"
    assert len(at.get("vega_lite_chart")) == 1
