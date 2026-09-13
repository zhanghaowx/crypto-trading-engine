import time

from streamlit.testing.v1 import AppTest

from jolteon.app.health_summary import (
    HEARTBEAT_TIMEOUT_SECONDS,
    is_down,
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
