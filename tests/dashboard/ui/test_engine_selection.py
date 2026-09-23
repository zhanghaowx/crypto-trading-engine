import pytest

from jolteon.dashboard.ui.engine_selection import (
    UNRECORDED_MODE,
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
