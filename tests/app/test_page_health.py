def test_shows_warning_when_db_missing(dashboard):
    at = dashboard.switch_page("app_pages/health.py").run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_heartbeats_recorded(dashboard, empty_db_path):
    dashboard.session_state["db_path"] = empty_db_path
    at = dashboard.switch_page("app_pages/health.py").run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No heartbeats recorded yet."


def test_renders_a_badge_per_sender(dashboard, populated_db_path):
    dashboard.session_state["db_path"] = populated_db_path
    at = dashboard.switch_page("app_pages/health.py").run()

    assert not at.exception
    assert at.markdown[0].value == "**MarketMaking**"
    assert "NORMAL" in at.markdown[1].value
    assert at.caption[0].value == "All good"
