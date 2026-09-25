from streamlit.testing.v1 import AppTest

from tests.dashboard.conftest import scoped_run


def _heading_script() -> None:
    from jolteon.dashboard.ui.page_header import page_heading

    page_heading("Live", "What this engine is doing right now.")


def test_a_page_heading_names_the_page_and_its_purpose():
    at = AppTest.from_function(_heading_script).run()

    assert not at.exception
    assert at.title[0].value == "Live"
    assert at.caption[0].value == "What this engine is doing right now."


def _scope_script() -> None:
    import streamlit as st

    from jolteon.dashboard.ui.page_header import run_scope_caption

    run_scope_caption(st.session_state.get("run"))


def test_a_runs_scope_is_captioned_with_its_status_and_mode():
    at = AppTest.from_function(_scope_script)
    at.session_state["run"] = scoped_run(
        "20260920T120000Z-deadbeef", status="stopped"
    )
    at.run()

    assert not at.exception
    assert at.caption[0].value == (
        "Run `deadbeef` · started 2026-09-20 00:00:00 UTC · "
        "Stopped · Paper · Live feed"
    )


def test_nothing_is_captioned_before_a_run_exists():
    at = AppTest.from_function(_scope_script).run()

    assert not at.exception
    assert not at.caption
