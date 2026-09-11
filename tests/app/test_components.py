from streamlit.testing.v1 import AppTest


def paginate_script():
    import pandas as pd
    import streamlit as st

    from jolteon.app.components import paginate

    total_rows = st.session_state.get("total_rows", 25)
    df = pd.DataFrame({"value": range(total_rows)})
    page, show_controls = paginate(df, key="demo", page_size=10)
    st.write(page["value"].tolist())
    show_controls()


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


def test_paginate_returns_whole_frame_with_no_controls_below_page_size():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 10
    at.run()

    assert not at.exception
    assert at.json[0].value == str(list(range(10)))
    assert not at.button
    assert not at.caption


def test_paginate_shows_the_first_page_with_previous_disabled():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 25
    at.run()

    assert not at.exception
    assert at.json[0].value == str(list(range(10)))
    # The current page's own button is disabled rather than clickable.
    assert at.button(key="demo-page-0").disabled
    assert not at.button(key="demo-page-1").disabled
    assert at.button(key="demo-prev-page").disabled
    assert not at.button(key="demo-next-page").disabled


def test_paginate_advancing_a_page_immediately_re_enables_previous():
    """Regression test: Previous used to stay disabled for one extra rerun
    after Next was clicked, because a local `page` variable was mutated
    only after Previous's own `disabled=` had already been evaluated - the
    button you'd just used to get past page 1 looked stuck disabled."""
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 25
    at.run()

    at.button(key="demo-next-page").click().run()

    assert not at.exception
    assert at.json[0].value == str(list(range(10, 20)))
    assert at.button(key="demo-page-1").disabled
    assert not at.button(key="demo-page-0").disabled
    assert not at.button(key="demo-prev-page").disabled
    assert not at.button(key="demo-next-page").disabled


def test_paginate_disables_next_on_the_last_page():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 25
    at.run()

    at.button(key="demo-next-page").click().run()
    at.button(key="demo-next-page").click().run()

    assert not at.exception
    assert at.json[0].value == str(list(range(20, 25)))
    assert at.button(key="demo-page-2").disabled
    assert at.button(key="demo-next-page").disabled
    assert not at.button(key="demo-prev-page").disabled


def test_paginate_jumps_straight_to_a_clicked_page_number():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 25
    at.run()

    at.button(key="demo-page-2").click().run()

    assert not at.exception
    assert at.json[0].value == str(list(range(20, 25)))
    assert at.button(key="demo-page-2").disabled
    assert not at.button(key="demo-page-0").disabled


def test_paginate_collapses_far_pages_behind_an_ellipsis():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 100
    at.run()

    assert not at.exception
    # 10 pages: only the first, its neighbor, and the last get a button -
    # the rest collapse into one ellipsis between them.
    assert at.button(key="demo-page-0").disabled
    assert not at.button(key="demo-page-1").disabled
    assert not at.button(key="demo-page-9").disabled
    assert at.button(key="demo-page-ellipsis-2").disabled
    assert len(at.button) == 6  # prev, 0, 1, ellipsis, 9, next


def test_paginate_previous_returns_to_the_first_page():
    at = AppTest.from_function(paginate_script)
    at.session_state["total_rows"] = 25
    at.run()

    at.button(key="demo-next-page").click().run()
    at.button(key="demo-prev-page").click().run()

    assert not at.exception
    assert at.json[0].value == str(list(range(10)))
    assert at.button(key="demo-page-0").disabled
    assert at.button(key="demo-prev-page").disabled
