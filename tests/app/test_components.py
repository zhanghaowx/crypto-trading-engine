from streamlit.testing.v1 import AppTest


def card_grid_script():
    import streamlit as st

    from jolteon.app.components import card_grid

    for item in card_grid(["a", "b", "c"], columns=2):
        st.write(item)


def card_grid_empty_script():
    import streamlit as st

    from jolteon.app.components import card_grid

    st.write(list(card_grid([], columns=2)))


def warn_if_no_db_script():
    import streamlit as st

    from jolteon.app.components import warn_if_no_db

    st.write(warn_if_no_db())


def test_card_grid_renders_every_item_in_a_bordered_container():
    at = AppTest.from_function(card_grid_script).run()

    assert not at.exception
    assert [m.value for m in at.markdown] == ["a", "b", "c"]
    # One bordered container per item, laid out inside column groups.
    assert len(at.columns) > 0


def test_card_grid_yields_nothing_for_an_empty_list():
    at = AppTest.from_function(card_grid_empty_script).run()

    assert not at.exception
    assert at.json[0].value == "[]"


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
