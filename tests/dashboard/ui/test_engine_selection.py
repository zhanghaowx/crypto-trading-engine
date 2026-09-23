from datetime import datetime, timezone

import pytest

from jolteon.dashboard.ui.engine_selection import (
    UNRECORDED_MODE,
    replay_source,
    run_mode,
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
