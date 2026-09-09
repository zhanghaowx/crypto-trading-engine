from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import parameters

    parameters.render()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert missing_db_path in at.warning[0].value
    assert not at.success


def test_shows_success_when_db_present(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert empty_db_path in at.success[0].value


def test_widgets_are_seeded_from_and_write_back_to_session_state(
    empty_db_path,
):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.session_state["auto_refresh"] = True
    at.session_state["refresh_seconds"] = 5
    at.run()

    assert not at.exception
    assert at.text_input(key="db_path").value == empty_db_path
    assert at.checkbox(key="auto_refresh").value is True
    assert at.slider(key="refresh_seconds").value == 5

    at.checkbox(key="auto_refresh").uncheck().run()

    assert not at.exception
    assert at.session_state["auto_refresh"] is False
