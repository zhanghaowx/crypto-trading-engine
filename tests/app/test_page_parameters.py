from pathlib import Path

from streamlit.testing.v1 import AppTest

_PARAMETERS_PAGE_PATH = str(
    Path(__file__).resolve().parents[2]
    / "jolteon"
    / "app"
    / "app_pages"
    / "parameters.py"
)


def test_shows_warning_when_db_missing(dashboard, missing_db_path):
    at = dashboard.switch_page("app_pages/parameters.py").run()

    assert not at.exception
    assert at.warning
    assert missing_db_path in at.warning[0].value
    assert not at.success


def test_shows_success_when_db_present(dashboard, empty_db_path):
    dashboard.session_state["db_path"] = empty_db_path
    at = dashboard.switch_page("app_pages/parameters.py").run()

    assert not at.exception
    assert not at.warning
    assert empty_db_path in at.success[0].value


def test_widgets_are_seeded_from_and_write_back_to_session_state(
    empty_db_path,
):
    # Loaded directly rather than through the dashboard entrypoint: this
    # page toggles auto_refresh to True, and the entrypoint's trailing
    # logic would take that as a cue to really sleep and st.rerun().
    # parameters.py has no navigation of its own, so it's safe to run
    # standalone.
    at = AppTest.from_file(_PARAMETERS_PAGE_PATH)
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
