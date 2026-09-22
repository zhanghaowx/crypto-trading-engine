import time

from streamlit.testing.v1 import AppTest

from jolteon.dashboard.services.health import HealthSummary
from jolteon.dashboard.ui.navigation import nav_alert_rule


def _read(engines, script) -> AppTest:
    at = AppTest.from_function(script)
    at.session_state["root"] = engines.root
    return at.run()


def test_a_quiet_nav_item_is_left_unmarked():
    quiet = HealthSummary(down=(), errors=0)

    assert 'span[label="Health"]' not in nav_alert_rule(quiet)


def test_an_alarmed_nav_item_is_marked_for_the_reader():
    """
    A navigation item has no badge to raise, so a dot is drawn after the
    item's own name.
    """
    alarmed = HealthSummary(down=("BTC/USD · MD",), errors=2)

    assert 'span[label="Health"]' in nav_alert_rule(alarmed)


def nav_script():
    import streamlit as st

    from jolteon.dashboard.services.health import HealthSummary
    from jolteon.dashboard.ui.navigation import (
        nav_drawn,
        redraw_nav_if_stale,
    )

    st.session_state["runs"] = st.session_state.get("runs", 0) + 1
    if st.session_state["runs"] == 1:
        nav_drawn(HealthSummary(down=("BTC/USD · MD",), errors=0))
    redraw_nav_if_stale(st.session_state.root)


def test_the_nav_is_redrawn_once_when_what_it_says_stops_being_true(engines):
    """
    Navigation is drawn by the entrypoint, which a fragment rerunning on
    its own timer never re-runs. One full rerun per change is the whole
    budget: asking on every refresh would undo fragments entirely, and a
    check that never records what it found would do exactly that.
    """
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, nav_script)

    assert not at.exception
    assert at.session_state["runs"] == 2


def test_nothing_is_redrawn_before_the_nav_has_been_drawn(engines):
    """
    A page rendered without the entrypoint has no navigation to correct,
    and asking for a rerun there would never stop.
    """
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, nav_script_without_drawing)

    assert not at.exception
    assert at.session_state["runs"] == 1


def nav_script_without_drawing():
    import streamlit as st

    from jolteon.dashboard.ui.navigation import redraw_nav_if_stale

    st.session_state["runs"] = st.session_state.get("runs", 0) + 1
    redraw_nav_if_stale(st.session_state.root)


def growing_errors_script():
    import streamlit as st

    from jolteon.dashboard.services.health import HealthSummary
    from jolteon.dashboard.ui.navigation import (
        nav_drawn,
        redraw_nav_if_stale,
    )

    st.session_state["runs"] = st.session_state.get("runs", 0) + 1
    if st.session_state["runs"] == 1:
        # The nav already carries its dot: one error was showing when it
        # was drawn, and more have been logged since.
        nav_drawn(HealthSummary(down=(), errors=1))
    redraw_nav_if_stale(st.session_state.root)


def test_more_of_an_alert_already_showing_does_not_redraw_the_page(engines):
    """
    Regression test: the navigation shows a dot or no dot, so a rising
    error count changes nothing about it. Comparing the whole summary
    reran the entire page every time an engine logged an error, which on
    a busy one is every few seconds - tearing down every card, re-reading
    the recording and redrawing every chart to no visible effect.
    """
    engines.add(
        "BTC/USD",
        heartbeats=[(time.time(), "MD", 1, "Streaming")],
        logs=[
            (str(time.time()), "jolteon", "ERROR", "f.py", "1", "one"),
            (str(time.time()), "jolteon", "ERROR", "f.py", "2", "two"),
            (str(time.time()), "jolteon", "ERROR", "f.py", "3", "three"),
        ],
    )

    at = _read(engines, growing_errors_script)

    assert not at.exception
    assert at.session_state["runs"] == 1


def alert_cleared_script():
    import streamlit as st

    from jolteon.dashboard.services.health import HealthSummary
    from jolteon.dashboard.ui.navigation import (
        nav_drawn,
        redraw_nav_if_stale,
    )

    st.session_state["runs"] = st.session_state.get("runs", 0) + 1
    if st.session_state["runs"] == 1:
        nav_drawn(HealthSummary(down=("BTC/USD · MD",), errors=4))
    redraw_nav_if_stale(st.session_state.root)


def test_the_nav_is_redrawn_when_the_last_alert_clears(engines):
    """The dot has to come off as well as go on, so the page is rerun
    once when nothing is left to alert about."""
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, alert_cleared_script)

    assert not at.exception
    assert at.session_state["runs"] == 2
