from pathlib import Path

from streamlit.testing.v1 import AppTest

_PAGE_PATH = str(
    Path(__file__).resolve().parents[2]
    / "jolteon"
    / "app"
    / "app_pages"
    / "parameters.py"
)


def _page(params_db_path, missing_db_path, engines) -> AppTest:
    at = AppTest.from_file(_PAGE_PATH)
    at.session_state["params_db_path"] = params_db_path
    at.session_state["db_path"] = missing_db_path
    at.session_state["log_db_path"] = missing_db_path
    at.session_state["root"] = engines.root
    at.session_state["auto_refresh"] = False
    at.session_state["refresh_seconds"] = 5
    return at


def test_opens_on_the_engine_tab(params_db_path, missing_db_path, engines):
    at = _page(params_db_path, missing_db_path, engines).run()

    assert not at.exception
    assert at.number_input
    assert not at.toggle


def test_the_tab_a_link_names_is_the_tab_that_opens(
    params_db_path, missing_db_path, engines
):
    at = _page(params_db_path, missing_db_path, engines)
    at.query_params["tab"] = "Dashboard"
    at.run()

    assert not at.exception
    assert at.toggle(key="auto_refresh")
    assert not at.number_input


def test_a_tab_nobody_has_falls_back_to_the_first(
    params_db_path, missing_db_path, engines
):
    """
    The parameter comes from the URL, so it is whatever was typed or
    whatever a rename left behind.
    """
    at = _page(params_db_path, missing_db_path, engines)
    at.query_params["tab"] = "Nope"
    at.run()

    assert not at.exception
    assert at.number_input


def test_switching_tabs_puts_the_tab_in_the_url(
    params_db_path, missing_db_path, engines
):
    at = _page(params_db_path, missing_db_path, engines).run()
    # A keyed tab is opened the way Streamlit reports one: through the
    # session state its key names.
    at.session_state["tab"] = "Dashboard"
    at.run()

    assert not at.exception
    assert at.query_params["tab"] == ["Dashboard"]


def test_the_tab_a_page_opens_on_is_left_out_of_the_url(
    params_db_path, missing_db_path, engines
):
    """
    A parameter left trailing behind would be carried into every link
    copied from the page.
    """
    at = _page(params_db_path, missing_db_path, engines)
    at.query_params["tab"] = "Dashboard"
    at.run()
    at.session_state["tab"] = "Engine"
    at.run()

    assert not at.exception
    assert "tab" not in at.query_params


def test_the_tab_that_is_shut_is_not_built(
    params_db_path, missing_db_path, engines
):
    """
    The Engine tab builds a widget for every tunable the catalog declares
    and reads what every engine did with them, which is work worth not
    doing while nobody is looking at it.
    """
    at = _page(params_db_path, missing_db_path, engines)
    at.query_params["tab"] = "Dashboard"
    at.run()

    assert not at.number_input
