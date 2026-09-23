from datetime import datetime, timezone
from unittest.mock import MagicMock

from jolteon.engine.core.engine_run import (
    EngineRun,
    ExecutionMode,
    MarketDataMode,
    engine_run_id,
    execution_mode_of,
    market_data_mode_of,
)


def test_run_ids_are_unique_and_carry_the_start_time():
    started = datetime(2026, 9, 20, 12, 34, 56, tzinfo=timezone.utc)

    first = engine_run_id(started)
    second = engine_run_id(started)

    assert first.startswith("20260920T123456Z-")
    assert first != second


def test_engine_run_uses_run_id_as_its_recording_identity():
    started = datetime(2026, 9, 20, tzinfo=timezone.utc)
    run = EngineRun("run-a", "Binance.US", "BTC/USD", started)

    assert run.PRIMARY_KEY == "run_id"
    assert run.ended_at is None


class _Simulated:
    execution_mode = ExecutionMode.SIMULATED


class _Real:
    execution_mode = ExecutionMode.REAL


class _Recorded:
    market_data_mode = MarketDataMode.RECORDED


class _Realtime:
    market_data_mode = MarketDataMode.REALTIME


def test_a_new_run_claims_neither_mode_until_it_is_wired():
    run = EngineRun(
        "run-a", "Binance.US", "BTC/USD", datetime.now(tz=timezone.utc)
    )

    assert run.execution_mode == ExecutionMode.UNKNOWN
    assert run.market_data_mode == MarketDataMode.UNKNOWN


def test_modes_come_from_the_components_that_claim_them():
    assert execution_mode_of(_Simulated()) == ExecutionMode.SIMULATED
    assert execution_mode_of(_Real()) == ExecutionMode.REAL
    assert market_data_mode_of(_Recorded()) == MarketDataMode.RECORDED
    assert market_data_mode_of(_Realtime()) == MarketDataMode.REALTIME


def test_a_component_claiming_nothing_leaves_the_mode_unknown():
    assert execution_mode_of(object()) == ExecutionMode.UNKNOWN
    assert market_data_mode_of(object()) == MarketDataMode.UNKNOWN


def test_a_component_claiming_something_else_leaves_the_mode_unknown():
    """A test double answering every attribute must not be read as a
    claim, or a mocked service would classify the run it was wired into."""
    mock = MagicMock()

    assert execution_mode_of(mock) == ExecutionMode.UNKNOWN
    assert market_data_mode_of(mock) == MarketDataMode.UNKNOWN


def test_modes_are_recorded_as_the_names_they_are_read_back_by():
    assert ExecutionMode.SIMULATED.value == "SIMULATED"
    assert MarketDataMode.RECORDED.value == "RECORDED"
