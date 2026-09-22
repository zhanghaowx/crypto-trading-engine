import sqlite3
import time
from dataclasses import replace
from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.services.health import (
    HEARTBEAT_TIMEOUT_SECONDS,
    HealthSummary,
    is_down,
    resolve_run,
)


def test_a_sender_heard_from_recently_is_not_down():
    assert not is_down(HEARTBEAT_TIMEOUT_SECONDS)


def test_a_sender_past_the_timeout_is_down():
    """
    Components heartbeat every 10s, so the timeout sits past two cycles:
    anything tighter flags a running engine on nearly every refresh.
    """
    assert is_down(HEARTBEAT_TIMEOUT_SECONDS + 1)


def _open_run(started_ago: float) -> RecordedEngineRun:
    return RecordedEngineRun(
        run_id="run-a",
        exchange="Kraken",
        symbol="BTC/USD",
        started_at=datetime.fromtimestamp(
            time.time() - started_ago, tz=timezone.utc
        ),
        ended_at=None,
        status="open",
    )


def _recording_with_heartbeat(tmp_path, seconds_ago: float | None) -> str:
    db_path = str(tmp_path / "engine.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE heartbeat (timestamp REAL, sender TEXT)")
        if seconds_ago is not None:
            conn.execute(
                "INSERT INTO heartbeat VALUES (?, 'MarketMaking')",
                (time.time() - seconds_ago,),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_an_open_run_still_heartbeating_is_running(tmp_path):
    db_path = _recording_with_heartbeat(tmp_path, seconds_ago=1.0)

    resolved = resolve_run(db_path, _open_run(started_ago=3600.0))

    assert resolved.status == "running"


def test_an_open_run_gone_quiet_is_interrupted(tmp_path):
    """
    A killed process never records its own end, so the recording alone
    would show it running forever. Silence is the only signal there is.
    """
    db_path = _recording_with_heartbeat(
        tmp_path, seconds_ago=HEARTBEAT_TIMEOUT_SECONDS + 1
    )

    resolved = resolve_run(db_path, _open_run(started_ago=3600.0))

    assert resolved.status == "interrupted"


def test_an_engine_that_has_not_heartbeat_yet_is_still_starting_up(tmp_path):
    db_path = _recording_with_heartbeat(tmp_path, seconds_ago=None)

    resolved = resolve_run(db_path, _open_run(started_ago=1.0))

    assert resolved.status == "running"


def test_an_engine_that_never_heartbeat_at_all_is_interrupted(tmp_path):
    db_path = _recording_with_heartbeat(tmp_path, seconds_ago=None)

    resolved = resolve_run(
        db_path, _open_run(started_ago=HEARTBEAT_TIMEOUT_SECONDS + 1)
    )

    assert resolved.status == "interrupted"


def test_a_settled_status_is_left_alone(tmp_path):
    db_path = _recording_with_heartbeat(tmp_path, seconds_ago=1.0)
    stopped = replace(_open_run(started_ago=1.0), status="stopped")

    assert resolve_run(db_path, stopped) is stopped
    assert resolve_run(db_path, None) is None


def _read(engines, script) -> AppTest:
    at = AppTest.from_function(script)
    at.session_state["root"] = engines.root
    return at.run()


def heartbeat_script():
    import streamlit as st

    from jolteon.dashboard.services.health import heartbeats

    st.session_state["found"] = heartbeats(st.session_state.root)


def error_script():
    import streamlit as st

    from jolteon.dashboard.data.engines import engine_databases
    from jolteon.dashboard.services.health import errors

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

    from jolteon.dashboard.services.health import summary

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
