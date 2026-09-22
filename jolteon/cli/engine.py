"""Command-line runner for live trading and historical replay."""

import argparse
import asyncio
import cProfile
import signal
import sys
import tempfile
from datetime import datetime, timezone

import pytz

from jolteon.cli.progress import ProgressBar
from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.market import Market
from jolteon.engine.core.parameter.live_parameter_service import (
    LiveParameterService,
)
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.core.sentry import reporting
from jolteon.engine.core.storage import paths
from jolteon.engine.market_data.data_source import DatabaseDataSource
from jolteon.engine.runtime.exchange_registry import exchange_definition
from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.inventory import (
    InventoryAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.momentum import (
    MomentumAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.order_flow_imbalance import (  # noqa: E501
    OrderFlowImbalanceAdjustment,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.quote_offset import (
    FeeAwareQuoteOffsetService,
)

_active_runtime = None


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    if _active_runtime is not None:
        # Cancels the MD thread's connection task so run_start() unblocks
        # and main() exits on its own; sys.exit() here would only unwind
        # the main thread and leave that thread's live feed running,
        # which is what used to hang shutdown.
        _active_runtime.request_shutdown()
    else:
        sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main():
    global _active_runtime
    started_at = datetime.now(tz=pytz.utc)

    parser = argparse.ArgumentParser(description="Jolteon Trading Engine")
    parser.add_argument("--replay-db", help="Path to a SQLite database file")
    parser.add_argument("--replay-start", help="Start time in ISO format")
    parser.add_argument("--replay-end", help="End time in ISO format")
    parser.add_argument("--exchange", help="Name of the exchange")
    parser.add_argument(
        "--symbol",
        default="BTC-USD",
        help=(
            "Symbol to trade, written either BASE-QUOTE or BASE/QUOTE. "
            "One engine trades one symbol, so run a process per symbol; "
            "each writes its own database for the dashboard to read."
        ),
    )
    parser.add_argument(
        "--root",
        default=paths.DEFAULT_ROOT,
        help=(
            "Directory every session writes under. Each symbol gets a "
            "directory of its own inside it, holding that session's "
            "recording and its log."
        ),
    )
    parser.add_argument(
        "--params-db",
        default=None,
        help=(
            "Path to the SQLite database the dashboard pushes parameter "
            "changes into. Defaults to one store at the root of --root, "
            "shared by every symbol. Pass an empty string to run on the "
            "declared defaults and ignore anything pushed."
        ),
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help=(
            "Live mode only: consume the exchange's real market data feed "
            "but send orders to a mock execution service instead of the "
            "real exchange (paper trading). Runs a market making strategy, "
            "tuned by the declared parameter defaults, or by whatever "
            "the dashboard has pushed into --params-db, so there is "
            "order/fill/risk-limit activity to watch on the dashboard."
        ),
    )

    # Access the arguments
    args = parser.parse_args()
    replay_start = args.replay_start
    replay_end = args.replay_end
    replay_db = args.replay_db
    symbol = getattr(args, "symbol", "BTC-USD")

    mode = (
        "replay"
        if (replay_start and replay_end) or replay_db
        else ("paper" if getattr(args, "paper", False) else "live")
    )
    reporting.configure(
        exchange=args.exchange,
        symbol=symbol,
        mode=mode,
        component="engine",
    )

    market = Market.parse(args.exchange)
    exchange = exchange_definition(market)
    if exchange.runtime is None or exchange.fee_schedule is None:
        raise NotImplementedError(
            f"A runtime is not implemented for market {args.exchange}"
        )
    build_runtime = exchange.runtime
    fee_schedule = exchange.fee_schedule

    # Every file a session writes goes under its own symbol's directory,
    # or a second engine would interleave its rows into the first one's
    # database.
    params_db = (
        paths.parameter_store(args.root, exchange.name)
        if args.params_db is None
        else args.params_db
    )

    if replay_start and replay_end and replay_db:
        assert False, (
            "No need to specify both replay start, "
            "end time and replay database path"
        )

    if (replay_start and replay_end) or replay_db:
        if replay_start and replay_end:
            replay_start_time = datetime.fromisoformat(replay_start).replace(
                tzinfo=timezone.utc
            )
            replay_end_time = datetime.fromisoformat(replay_end).replace(
                tzinfo=timezone.utc
            )
        else:
            data_source = DatabaseDataSource(replay_db)
            replay_start_time = data_source.start_time()
            replay_end_time = data_source.end_time()

        print(f"Replay Start: {replay_start_time}")
        print(f"Replay End  : {replay_end_time}")
        runtime = build_runtime(
            symbol,
            use_mock_execution=True,
            database_name=paths.recording(
                args.root, exchange.name, symbol, paths.REPLAY
            ),
            logfile_name=paths.log_file(
                args.root, exchange.name, symbol, paths.REPLAY
            ),
        )
        _active_runtime = runtime
        profiler = cProfile.Profile()
        profiler.enable()

        pb = ProgressBar(replay_start_time, replay_end_time)
        pb.start()
        if replay_start and replay_end:
            pnl = await runtime.run_replay(replay_start_time, replay_end_time)
        else:
            pnl = await runtime.run_local_replay(replay_db)
        pb.stop()

        profiler.disable()
        profiler.dump_stats(f"{tempfile.gettempdir()}/jolteon.stat")

    else:
        strategy = None
        fair_price_model = None
        health_monitor = HealthMonitor()
        # Only a live session polls. A replay installs fake time and has
        # to produce the same result twice, which it cannot if a
        # dashboard can retune it halfway through.
        parameter_service = (
            LiveParameterService(params_db, health_monitor=health_monitor)
            if params_db
            else StaticParameterService(health_monitor=health_monitor)
        )
        if args.paper:
            strategy_symbol = symbol.replace("-", "/")
            quote_offset_service = FeeAwareQuoteOffsetService(
                fee_schedule=fee_schedule,
                parameter_service=parameter_service,
            )
            # Shared with PostTradeService below, so decorated fills are
            # scored against the same fair price the strategy quotes off.
            fair_price_model = AdjustedFairPriceModel(
                base=MidPriceFairPriceModel(),
                adjustments=[
                    MomentumAdjustment(parameter_service=parameter_service),
                    OrderFlowImbalanceAdjustment(
                        parameter_service=parameter_service
                    ),
                    InventoryAdjustment(parameter_service=parameter_service),
                ],
                parameter_service=parameter_service,
            )
            strategy = MarketMakingStrategy(
                symbol=strategy_symbol,
                fair_price_model=fair_price_model,
                parameter_service=parameter_service,
                quote_offset_service=quote_offset_service,
                health_monitor=health_monitor,
            )

        runtime = build_runtime(
            symbol,
            use_mock_execution=args.paper,
            database_name=paths.recording(args.root, exchange.name, symbol),
            logfile_name=paths.log_file(args.root, exchange.name, symbol),
            strategy=strategy,
            fair_price_model=fair_price_model,
            parameter_service=parameter_service,
            health_monitor=health_monitor,
        )
        _active_runtime = runtime
        pnl = await runtime.start()

    _active_runtime = None
    print(f"PnL: {pnl}")

    ended_at = datetime.now(tz=pytz.utc)
    print(f"Total Runtime: {ended_at - started_at}")


if __name__ == "__main__":
    asyncio.run(main())
