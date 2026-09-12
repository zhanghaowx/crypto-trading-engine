from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import viewer_settings

    viewer_settings.render()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.session_state["log_db_path"] = missing_db_path
    at.session_state["params_db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert len(at.warning) == 2
    assert missing_db_path in at.warning[0].value
    assert not at.success


def test_shows_success_when_db_present(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.session_state["log_db_path"] = empty_db_path
    at.session_state["params_db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert len(at.success) == 2
    assert empty_db_path in at.success[0].value


def test_widgets_are_seeded_from_and_write_back_to_session_state(
    empty_db_path,
):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.session_state["log_db_path"] = empty_db_path
    at.session_state["params_db_path"] = empty_db_path
    at.session_state["auto_refresh"] = True
    at.session_state["refresh_seconds"] = 5
    at.session_state["chart_window_minutes"] = 15
    at.run()

    assert not at.exception
    assert at.text_input(key="db_path").value == empty_db_path
    assert at.text_input(key="log_db_path").value == empty_db_path
    assert at.checkbox(key="auto_refresh").value is True
    assert at.slider(key="refresh_seconds").value == 5
    assert at.slider(key="chart_window_minutes").value == 15

    at.checkbox(key="auto_refresh").uncheck().run()

    assert not at.exception
    assert at.session_state["auto_refresh"] is False
