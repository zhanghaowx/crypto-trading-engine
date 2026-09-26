from streamlit.testing.v1 import AppTest

from tests.dashboard.conftest import scoped_run


def _scope_script() -> None:
    import streamlit as st

    from jolteon.dashboard.ui.page_header import context_bar

    with context_bar(
        st.session_state.get("run"), live=st.session_state.get("live", False)
    ):
        st.write("picker")


def _badges(at) -> str:
    # st.badge reaches AppTest as markdown, as ":gray-badge[Stopped]".
    return " ".join(m.value for m in at.markdown if "-badge[" in m.value)


def _dot(at) -> str:
    """The live dot's classes: whether it is pulsing or drained."""
    for h in at.get("html"):
        if "jolteon-live-dot" in h.body and "<style>" not in h.body:
            return h.body.split('class="', 1)[1].split('"', 1)[0]
    return ""


def test_a_runs_scope_is_badged_with_its_status_and_both_of_its_modes():
    at = AppTest.from_function(_scope_script)
    at.session_state["run"] = scoped_run(
        "20260920T120000Z-deadbeef", status="stopped"
    )
    at.run()

    assert not at.exception
    badges = _badges(at)
    assert ":gray-badge[Stopped]" in badges
    # How it executed and where its data came from are two facts, so
    # they are two badges.
    assert ":blue-badge[Paper]" in badges
    assert ":green-badge[Live feed]" in badges
    assert at.caption[0].value == (
        "Run `deadbeef` · started 2026-09-20 00:00:00 UTC"
    )


def test_a_runs_status_colors_its_own_badge():
    at = AppTest.from_function(_scope_script)
    at.session_state["run"] = scoped_run(
        "20260920T120000Z-deadbeef", status="interrupted"
    )
    at.run()

    assert not at.exception
    assert ":orange-badge[Interrupted]" in _badges(at)


def test_the_pages_own_pickers_come_before_the_runs_badges():
    at = AppTest.from_function(_scope_script)
    at.session_state["run"] = scoped_run("20260920T120000Z-deadbeef")
    at.run()

    values = [m.value for m in at.markdown]
    assert values.index("picker") < values.index(":green-badge[Running]")


def test_nothing_is_said_about_a_run_before_one_exists():
    at = AppTest.from_function(_scope_script).run()

    assert not at.exception
    assert not at.caption
    assert not _badges(at)
    assert not at.segmented_control


def test_a_live_page_says_how_often_it_refreshes_and_offers_to_stop():
    at = AppTest.from_function(_scope_script)
    at.session_state["live"] = True
    at.session_state["auto_refresh"] = True
    at.session_state["refresh_seconds"] = 5
    at.run()

    assert not at.exception
    assert at.caption[0].value == "Refreshing every 5 s"
    feed = at.segmented_control(key="live-feed-state")
    assert feed.value == "Live"
    assert _dot(at) == "jolteon-live-dot"


def test_pausing_the_feed_switches_refreshing_off_for_every_card():
    at = AppTest.from_function(_scope_script)
    at.session_state["live"] = True
    at.session_state["auto_refresh"] = True
    at.session_state["refresh_seconds"] = 5
    at.run()

    at.segmented_control(key="live-feed-state").set_value("Paused").run()

    assert not at.exception
    assert at.session_state["auto_refresh"] is False
    assert at.caption[0].value == "Paused"
    # The dot stays where it was and loses its color, so both states sit
    # in the same spot.
    assert _dot(at) == "jolteon-live-dot paused"


def test_refreshing_switched_off_elsewhere_reads_as_paused_here():
    """The settings page holds the same switch, so the feed control has
    to follow the setting rather than remember its own last click."""
    at = AppTest.from_function(_scope_script)
    at.session_state["live"] = True
    at.session_state["auto_refresh"] = False
    at.run()

    assert not at.exception
    assert at.segmented_control(key="live-feed-state").value == "Paused"
    assert at.caption[0].value == "Paused"


def _scope_bar_script() -> None:
    import streamlit as st

    from jolteon.dashboard.ui.page_header import scope_bar, scope_bar_end

    with scope_bar():
        st.write("start")
        with scope_bar_end():
            st.write("end")


def test_a_scope_bar_is_a_white_surface_with_its_end_pushed_away():
    at = AppTest.from_function(_scope_bar_script).run()

    assert not at.exception
    assert [m.value for m in at.markdown] == ["start", "end"]
    rules = " ".join(h.body for h in at.get("html"))
    assert ".st-key-run-scope-bar {" in rules
    assert "st-key-run-scope-end" in rules
