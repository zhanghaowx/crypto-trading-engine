from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import health

    health.render()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_heartbeats_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No heartbeats recorded yet."


def test_renders_a_badge_per_sender(live_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = live_db_path
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "**MarketMaking**"
    assert "NORMAL" in at.markdown[1].value
    assert at.caption[0].value.startswith("All good · Last seen ")


def test_reports_a_silent_sender_as_down(populated_db_path):
    """The recorded level is NORMAL, but the heartbeat is years old: a
    component that dies leaves its last cheerful row behind, so silence has
    to outrank what that row says."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.run()

    assert not at.exception
    assert "DOWN" in at.markdown[1].value
    assert "No heartbeat for" in at.caption[0].value
