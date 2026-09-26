"""Compose the normal Binance.US paper strategy for a bounded replay."""

import asyncio
import hashlib
import json
import logging
import platform
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from jolteon.engine.core.code_version import commit_sha, working_tree_is_clean
from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.parameter.parameter_service import (
    parameter_service,
    use_parameter_service,
)
from jolteon.engine.core.parameter.replay_parameters import ReplayParameters
from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.manifest_feed import ManifestFeed
from jolteon.engine.runtime.engine_runtime import EngineRuntime
from jolteon.engine.runtime.paper_strategy import paper_strategy
from jolteon.engine.runtime.replay_result import ReplayResult


def source_code_hash() -> str:
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _save(path: Path, metadata: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


async def run_replay(manifest, recording, output: Path, playback=None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": 1,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest.document,
        "input_hash": recording.input_hash,
        "input_counts": recording.counts,
        "ordering_policy": recording.ordering_policy,
        "limitations": recording.limitations,
        "code_hash": source_code_hash(),
        "commit": commit_sha(),
        "working_tree_clean": working_tree_is_clean(),
        "python_version": platform.python_version(),
    }
    metadata_path = output / "result.json"
    _save(metadata_path, metadata)
    capture = ReplayResult(output / "events.jsonl")
    runtime = None
    previous_parameters = parameter_service()
    logger = logging.getLogger()
    original_handlers = {
        handler: handler.formatter for handler in logger.handlers
    }
    original_level = logger.level
    try:
        monitor = HealthMonitor()
        parameters = ReplayParameters(recording.parameters)
        use_parameter_service(parameters)
        strategy, fair = paper_strategy(
            "BTC/USD",
            parameters,
            BinanceUsFeeSchedule,
            monitor,
        )
        runtime = EngineRuntime(
            "BTC/USD",
            str(output / "recording.sqlite"),
            str(output / "run.log"),
            exchange="Binance.US",
            strategy=strategy,
            fair_price_model=fair,
            parameter_service=parameters,
            health_monitor=monitor,
        )
        feed = ManifestFeed(manifest, recording, parameters, monitor, playback)
        runtime.use_execution_service(
            MockExecutionService(BinanceUsFeeSchedule, health_monitor=monitor)
        )
        runtime.use_market_data_service(feed)
        runtime._engine_run.market_data_source = str(manifest.source)
        runtime._engine_run.source_run_id = manifest.document["source"][
            "source_run_id"
        ]
        runtime._engine_run.market_data_started_at = datetime.fromtimestamp(
            manifest.start, timezone.utc
        )
        runtime._engine_run.market_data_ended_at = datetime.fromtimestamp(
            manifest.end, timezone.utc
        )
        capture.start()
        # One event loop lets failures propagate to result metadata.
        previous = EngineRuntime.THREAD_ENABLED
        EngineRuntime.THREAD_ENABLED = False
        try:
            await runtime.run_start()
        finally:
            EngineRuntime.THREAD_ENABLED = previous
        position = runtime._position_manager
        metadata.update(
            status="completed",
            output_counts=capture.counts,
            delivered_events=feed.delivered,
            max_lag_seconds=feed.playback.max_lag_seconds,
            terminal={
                "positions": {
                    symbol: value.volume
                    for symbol, value in position.positions.items()
                },
                "net_cash": position.pnl,
                "marked_pnl": position.total_pnl,
                "working_orders": list(capture.working.values()),
            },
        )
    except BaseException as error:
        metadata.update(
            status="interrupted"
            if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt))
            else "failed",
            error=f"{type(error).__name__}: {error}",
        )
        raise
    finally:
        capture.close()
        try:
            with ExitStack() as cleanup:
                if runtime is not None:
                    cleanup.callback(runtime._signal_recorder.close)
                for handler in list(logger.handlers):
                    if handler not in original_handlers:
                        logger.removeHandler(handler)
                        cleanup.callback(handler.close)
                    else:
                        handler.setFormatter(original_handlers[handler])
                logger.setLevel(original_level)
        except Exception as error:
            metadata.update(status="failed", error=f"Cleanup failed: {error}")
            raise
        finally:
            use_parameter_service(previous_parameters)
            metadata["ended_at"] = datetime.now(timezone.utc).isoformat()
            _save(metadata_path, metadata)
    return metadata
