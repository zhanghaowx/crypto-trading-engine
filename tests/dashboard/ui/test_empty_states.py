from streamlit.testing.v1 import AppTest


def warn_if_no_db_script():
    import streamlit as st

    from jolteon.dashboard.ui.empty_states import warn_if_no_db

    st.write(warn_if_no_db())


def test_warn_if_no_db_returns_false_and_warns_when_missing(missing_db_path):
    at = AppTest.from_function(warn_if_no_db_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert missing_db_path in at.warning[0].value
    assert at.markdown[-1].value == "`False`"


def test_warn_if_no_db_returns_true_and_does_not_warn_when_present(
    empty_db_path,
):
    at = AppTest.from_function(warn_if_no_db_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert at.markdown[-1].value == "`True`"
