from datetime import datetime, timezone

import pytest
from streamlit.testing.v1 import AppTest

from jolteon.dashboard.ui.engine_selection import (
    UNRECORDED_MODE,
    replay_source,
    run_mode,
    run_mode_badges,
    run_status,
)
from tests.dashboard.conftest import scoped_run


@pytest.mark.parametrize(
    ("execution_mode", "market_data_mode", "expected"),
    [
        ("SIMULATED", "REALTIME", "Paper · Live feed"),
        ("SIMULATED", "RECORDED", "Simulation · Replay"),
        ("REAL", "REALTIME", "Live · Live feed"),
        ("REAL", "RECORDED", "Live · Replay"),
    ],
)
def test_a_run_is_named_by_both_of_its_modes(
    execution_mode, market_data_mode, expected
):
    run = scoped_run(
        "run-a",
        execution_mode=execution_mode,
        market_data_mode=market_data_mode,
    )

    assert run_mode(run) == expected


@pytest.mark.parametrize(
    ("execution_mode", "market_data_mode"),
    [("UNKNOWN", "UNKNOWN"), ("SIMULATED", "UNKNOWN"), ("", "")],
)
def test_a_run_missing_a_mode_is_said_to_be_unclassified(
    execution_mode, market_data_mode
):
    run = scoped_run(
        "run-a",
        execution_mode=execution_mode,
        market_data_mode=market_data_mode,
    )

    assert run_mode(run) == UNRECORDED_MODE


def test_a_runs_two_modes_are_two_badges_and_real_money_is_the_warm_one():
    paper = scoped_run("run-a")
    real = scoped_run(
        "run-b", execution_mode="REAL", market_data_mode="RECORDED"
    )

    assert run_mode_badges(paper) == [
        ("Paper", "blue"),
        ("Live feed", "green"),
    ]
    assert run_mode_badges(real) == [("Live", "orange"), ("Replay", "blue")]


def test_a_run_missing_a_mode_wears_one_grey_badge_saying_so():
    run = scoped_run("run-a", execution_mode="", market_data_mode="")

    assert run_mode_badges(run) == [(UNRECORDED_MODE, "gray")]


def _select_script() -> None:
    from jolteon.dashboard.ui.engine_selection import select_engine

    select_engine()


def test_one_engine_alone_is_named_rather_than_offered(engines):
    """The scope bar still has to say whose recording the page reads."""
    engines.add("BTC/USD")
    at = AppTest.from_function(_select_script)
    at.session_state["root"] = engines.root
    at.run()

    assert not at.exception
    assert not at.segmented_control
    assert [m.value for m in at.markdown] == ["**Kraken · BTC/USD**"]


def test_nothing_is_named_before_an_engine_has_recorded(engines):
    at = AppTest.from_function(_select_script)
    at.session_state["root"] = engines.root
    at.run()

    assert not at.exception
    assert not at.markdown


def test_how_a_run_executed_is_separate_from_whether_it_finished():
    stopped = scoped_run("run-a", status="stopped")
    running = scoped_run("run-b", status="running")

    assert run_status(stopped) == "Stopped"
    assert run_status(running) == "Running"
    assert run_mode(stopped) == run_mode(running) == "Paper · Live feed"


def test_a_replay_says_which_recording_and_slice_it_read():
    run = scoped_run(
        "run-a",
        market_data_mode="RECORDED",
        market_data_source="/recordings/live.sqlite",
        source_run_id="20260920T100000Z-abc123",
        market_data_started_at=datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
        market_data_ended_at=datetime(2026, 9, 20, 11, tzinfo=timezone.utc),
        market_data_trade_count=4211,
    )

    assert replay_source(run) == (
        "Replayed `/recordings/live.sqlite` · "
        "2026-09-20 10:00:00 – 2026-09-20 11:00:00 UTC · "
        "4,211 market trades · recorded by run `abc123`"
    )


def test_a_replay_says_only_what_was_recorded_about_its_data():
    run = scoped_run(
        "run-a",
        market_data_mode="RECORDED",
        market_data_source="KrakenHistoricalDataSource",
    )

    assert replay_source(run) == "Replayed `KrakenHistoricalDataSource`"


def test_a_run_off_a_live_feed_has_no_replay_source():
    assert replay_source(scoped_run("run-a")) is None
