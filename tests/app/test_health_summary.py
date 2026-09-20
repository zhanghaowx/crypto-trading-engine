import time

from streamlit.testing.v1 import AppTest

from jolteon.app.health_summary import (
    HEARTBEAT_TIMEOUT_SECONDS,
    HealthSummary,
    is_down,
    nav_alert_rule,
)


def test_a_sender_heard_from_recently_is_not_down():
    assert not is_down(HEARTBEAT_TIMEOUT_SECONDS)


def test_a_sender_past_the_timeout_is_down():
    """
    Components heartbeat every 10s, so the timeout sits past two cycles:
    anything tighter flags a running engine on nearly every refresh.
    """
    assert is_down(HEARTBEAT_TIMEOUT_SECONDS + 1)


def _read(engines, script) -> AppTest:
    at = AppTest.from_function(script)
    at.session_state["root"] = engines.root
    return at.run()


def heartbeat_script():
    import streamlit as st

    from jolteon.app.health_summary import heartbeats

    st.session_state["found"] = heartbeats(st.session_state.root)


def error_script():
    import streamlit as st

    from jolteon.app.data import engine_databases
    from jolteon.app.health_summary import errors

    st.session_state["found"] = errors(engine_databases(st.session_state.root))


def test_a_heartbeat_names_the_symbol_whose_engine_sent_it(engines):
    """
    A sender is named for the job it does, so `MD` says nothing about
    which engine went quiet. The file it was read from is the only place
    that fact exists.
    """
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])
    engines.add("ETH/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, heartbeat_script)

    assert not at.exception
    assert sorted(at.session_state["found"]["symbol"]) == [
        "BTC/USD",
        "ETH/USD",
    ]


def test_no_engines_have_no_heartbeats(engines):
    at = _read(engines, heartbeat_script)

    assert at.session_state["found"].empty


def test_an_engine_yet_to_heartbeat_is_left_out(engines):
    engines.add("BTC/USD")
    engines.add("ETH/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, heartbeat_script)

    assert list(at.session_state["found"]["symbol"]) == ["ETH/USD"]


def _line(created: str, level: str = "ERROR", msg: str = "dropped"):
    return (created, "jolteon", level, "feed.py", "42", msg)


def test_an_error_names_the_symbol_whose_engine_logged_it(engines):
    engines.add("ETH/USD", logs=[_line("1700000000.0")])

    at = _read(engines, error_script)

    assert not at.exception
    assert list(at.session_state["found"]["symbol"]) == ["ETH/USD"]


def test_errors_from_every_engine_come_back_newest_first(engines):
    engines.add("BTC/USD", logs=[_line("1700000000.0", msg="older")])
    engines.add("ETH/USD", logs=[_line("1700000002.0", msg="newest")])

    at = _read(engines, error_script)

    assert list(at.session_state["found"]["msg"]) == ["newest", "older"]


def test_lines_below_error_are_not_errors(engines):
    engines.add("BTC/USD", logs=[_line("1700000000.0", level="WARNING")])

    at = _read(engines, error_script)

    assert at.session_state["found"].empty


def test_no_engines_have_no_errors(engines):
    at = _read(engines, error_script)

    assert at.session_state["found"].empty


def summary_script():
    import streamlit as st

    from jolteon.app.health_summary import summary

    st.session_state["found"] = summary(st.session_state.root)


def test_a_quiet_root_raises_nothing(engines):
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _read(engines, summary_script)

    assert at.session_state["found"] == HealthSummary(down=(), errors=0)


def test_a_silent_component_is_named_with_its_symbol(engines):
    engines.add("BTC/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])
    engines.add(
        "ETH/USD",
        heartbeats=[(time.time() - 600, "MarketMaking", 1, "All good")],
    )

    at = _read(engines, summary_script)

    assert at.session_state["found"].down == (
        "Kraken · ETH/USD · MarketMaking",
    )


def test_an_engine_yet_to_heartbeat_is_not_called_down(engines):
    """
    There is nothing to have stopped. Its own tiles say it has not
    started reporting; the navigation must not call that a failure.
    """
    engines.add("BTC/USD")

    at = _read(engines, summary_script)

    assert at.session_state["found"] == HealthSummary(down=(), errors=0)


def test_every_engines_errors_are_counted(engines):
    engines.add("BTC/USD", logs=[_line("1700000000.0")])
    engines.add(
        "ETH/USD",
        logs=[_line("1700000001.0"), _line("1700000002.0", level="CRITICAL")],
    )

    at = _read(engines, summary_script)

    assert at.session_state["found"].errors == 3


def test_lines_below_error_are_not_counted(engines):
    engines.add("BTC/USD", logs=[_line("1700000000.0", level="WARNING")])

    at = _read(engines, summary_script)

    assert at.session_state["found"].errors == 0


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

    from jolteon.app.health_summary import (
        HealthSummary,
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

    from jolteon.app.health_summary import redraw_nav_if_stale

    st.session_state["runs"] = st.session_state.get("runs", 0) + 1
    redraw_nav_if_stale(st.session_state.root)


def growing_errors_script():
    import streamlit as st

    from jolteon.app.health_summary import (
        HealthSummary,
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

    from jolteon.app.health_summary import (
        HealthSummary,
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
