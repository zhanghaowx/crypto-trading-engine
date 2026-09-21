import sqlite3
import time

import pytest
from streamlit.testing.v1 import AppTest

TODAY = "2023-11-14"
_OPENS = 1699920000.0


def _script():
    from jolteon.app.app_pages import engine_runs

    engine_runs.render()


def _page(engines) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    at.session_state["session_id"] = TODAY
    return at


def _record(recording: str, session_runs, runs) -> None:
    conn = sqlite3.connect(recording)
    try:
        conn.execute(
            "CREATE TABLE trading_session_run "
            "(session_run_id TEXT PRIMARY KEY, session_id TEXT, "
            "run_id TEXT, exchange TEXT, symbol TEXT, "
            "first_seen_at REAL, last_seen_at REAL)"
        )
        conn.executemany(
            "INSERT INTO trading_session_run VALUES "
            "(?, ?, ?, 'Kraken', 'BTC/USD', ?, ?)",
            [
                (f"{session}@{run}", session, run, first, last)
                for session, run, first, last in session_runs
            ],
        )
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES (?, 'Kraken', 'BTC/USD', ?, ?)",
            runs,
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def one_engine(engines):
    """An engine whose recording a test can add runs to."""
    engines.recording = engines.add("BTC/USD")
    return engines


def test_says_so_before_any_session_has_been_recorded(one_engine):
    at = _page(one_engine)
    at.session_state["session_id"] = None
    at.run()

    assert not at.exception
    assert "No trading session recorded yet." in [i.value for i in at.info]


def test_says_so_when_the_engine_did_not_trade_that_session(one_engine):
    _record(one_engine.recording, [], [])
    at = _page(one_engine).run()

    assert not at.exception
    assert f"Nothing recorded in {TODAY}." in [i.value for i in at.info]


def test_shows_every_run_that_traded_the_session(one_engine, table_lookup):
    _record(
        one_engine.recording,
        [
            (TODAY, "morning", _OPENS, _OPENS + 3600),
            (TODAY, "afternoon", _OPENS + 7200, _OPENS + 9000),
        ],
        [
            ("morning", _OPENS, None),
            ("afternoon", _OPENS + 7200, _OPENS + 9000),
        ],
    )
    at = _page(one_engine).run()

    assert not at.exception
    assert f"**Trading session {TODAY}**" in [m.value for m in at.markdown]
    rows = table_lookup(at, 0, "Run")
    assert set(rows) == {"morning", "afternoon"}
    assert rows["afternoon"]["Outcome"] == "Stopped"
    # Started this morning, never recorded an end, and silent since.
    assert rows["morning"]["Outcome"] == "Ended without stopping"


def test_a_run_still_recording_reads_as_running(one_engine, table_lookup):
    now = time.time()
    _record(
        one_engine.recording,
        [(TODAY, "live", now - 60, now)],
        [("live", now - 60, None)],
    )
    at = _page(one_engine).run()

    assert not at.exception
    assert table_lookup(at, 0, "Run")["live"]["Outcome"] == "Running"


def test_warns_when_no_engine_has_recorded_anything(engines):
    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    at.session_state["session_id"] = TODAY
    at.run()

    assert not at.exception
    assert engines.root in at.warning[0].value


def test_names_each_engine_while_more_than_one_has_traded(engines):
    """A restart matters to the engine it happened to, and the runs of
    two engines would otherwise read as one list."""
    for symbol in ("BTC/USD", "ETH/USD"):
        _record(
            engines.add(symbol),
            [(TODAY, "run-a", _OPENS, _OPENS + 3600)],
            [("run-a", _OPENS, _OPENS + 3600)],
        )

    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    at.session_state["session_id"] = TODAY
    at.run()

    assert not at.exception
    assert [m.value for m in at.markdown if m.value.startswith("**")] == [
        f"**Trading session {TODAY}**",
        "**Kraken · BTC/USD**",
        "**Kraken · ETH/USD**",
    ]
