from datetime import datetime, timezone

from jolteon.engine.core.engine_run import EngineRun, engine_run_id


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
