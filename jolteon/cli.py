"""
CLI interface for jolteon project.
"""

import argparse
import asyncio
import cProfile
import signal
import sys
import tempfile
from datetime import datetime, timezone

import pytz

from jolteon.app.progress_bar import ProgressBar
from jolteon.engine.core.market import Market
from jolteon.engine.market_data.data_source import DatabaseDataSource
from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.parameters import (
    StaticParameterService,
)

_active_app = None


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    if _active_app is not None:
        # Cancels the MD thread's connection task so run_start() unblocks
        # and main() exits on its own; sys.exit() here would only unwind
        # the main thread and leave that thread's live feed running,
        # which is what used to hang shutdown.
        _active_app.request_shutdown()
    else:
        sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main():
    global _active_app
    app_start_time = datetime.now(tz=pytz.utc)

    parser = argparse.ArgumentParser(description="Jolteon Trading Engine")
    parser.add_argument("--replay-db", help="Path to a SQLite database file")
    parser.add_argument("--replay-start", help="Start time in ISO format")
    parser.add_argument("--replay-end", help="End time in ISO format")
    parser.add_argument("--exchange", help="Name of the exchange")
    parser.add_argument(
        "--paper",
        action="store_true",
        help=(
            "Live mode only: consume the exchange's real market data feed "
            "but send orders to a mock execution service instead of the "
            "real exchange (paper trading). Runs a market making strategy, "
            "tuned by IParameterService's defaults, so there is order/"
            "fill/risk-limit activity to watch on the dashboard."
        ),
    )

    # Access the arguments
    args = parser.parse_args()
    replay_start = args.replay_start
    replay_end = args.replay_end
    replay_db = args.replay_db

    # Instantiate the correct market's application instance
    market = Market.parse(args.exchange)
    if market == Market.KRAKEN:
        from jolteon.app.kraken import KrakenApplication as Application
    elif market == Market.COINBASE:
        from jolteon.app.coinbase import CoinbaseApplication as Application
    else:
        raise NotImplementedError(
            f"Application is not implemented for market {args.exchange}"
        )

    symbol = "BTC-USD"

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
        app = Application(
            symbol,
            use_mock_execution=True,
            database_name="/tmp/replay.sqlite",
            logfile_name="/tmp/replay.log",
        )
        _active_app = app
        profiler = cProfile.Profile()
        profiler.enable()

        pb = ProgressBar(replay_start_time, replay_end_time)
        pb.start()
        if replay_start and replay_end:
            pnl = await app.run_replay(replay_start_time, replay_end_time)
        else:
            pnl = await app.run_local_replay(replay_db)
        pb.stop()

        profiler.disable()
        profiler.dump_stats(f"{tempfile.gettempdir()}/jolteon.stat")

    else:
        strategy = None
        fair_price_model = None
        if args.paper:
            # Kraken trades on "BTC/USD"; other exchanges keep "BTC-USD".
            strategy_symbol = (
                symbol.replace("-", "/") if market == Market.KRAKEN else symbol
            )
            # Shared with PostTradeService below, so decorated fills are
            # scored against the same fair price the strategy quotes off.
            # Signals land in `adjustments` below (STRATEGY.md Part 3).
            fair_price_model = AdjustedFairPriceModel(
                base=MidPriceFairPriceModel(),
                adjustments=[],
                max_adjustment=StaticParameterService.DEFAULT_HALF_SPREAD,
            )
            strategy = MarketMakingStrategy(
                symbol=strategy_symbol, fair_price_model=fair_price_model
            )

        app = Application(
            symbol,
            use_mock_execution=args.paper,
            database_name="/tmp/jolteon.sqlite",
            logfile_name="/tmp/jolteon.log",
            strategy=strategy,
            fair_price_model=fair_price_model,
        )
        _active_app = app
        pnl = await app.start()

    _active_app = None
    print(f"PnL: {pnl}")

    app_end_time = datetime.now(tz=pytz.utc)
    print(f"Total Runtime: {app_end_time - app_start_time}")


if __name__ == "__main__":
    asyncio.run(main())
