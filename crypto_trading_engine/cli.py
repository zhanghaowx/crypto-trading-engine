"""
CLI interface for crypto_trading_engine project.
"""
import logging
import signal
import sys
from datetime import datetime

import numpy as np
import pytz

from crypto_trading_engine.app import Application
from crypto_trading_engine.core.time.time_manager import time_manager
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main(training: bool = False):
    replay_start = datetime(
        2024, 1, 14, hour=21, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 14, hour=22, minute=59, second=0, tzinfo=pytz.utc
    )

    async def run_once(parameters: Parameters = Parameters()):
        app = Application(
            "ETH-USD",
            candlestick_interval_in_seconds=60,
            strategy_parameters=parameters,
        )

        pnl = await app.run_replay(replay_start, replay_end)
        logging.info(f"PnL: {pnl}, Parameters: {parameters}")

        # Prepare for next iteration
        time_manager().force_reset()

        return pnl

    async def run_training():
        result = dict[float, Parameters]()

        # Start Training
        for extreme_bullish_threshold in np.arange(2.0, 3.0, 0.1):
            for extreme_bullish_return_pct in np.arange(0.0001, 0.005, 0.001):
                for consolidation_threshold in np.arange(0.1, 0.3, 0.05):
                    parameters = Parameters(
                        max_number_of_recent_candlesticks=10,
                        extreme_bullish_threshold=extreme_bullish_threshold,
                        extreme_bullish_return_pct=extreme_bullish_return_pct,
                        consolidation_period_threshold=consolidation_threshold,
                    )
                    pnl = await run_once(parameters)

                    if pnl > 0.0:
                        result[pnl] = parameters

                # Prepare for next iteration
                time_manager().force_reset()

        if len(result) == 0:
            logging.warning("No best parameters found. Exiting...")
        else:
            sorted_dict = dict(
                sorted(result.items(), key=lambda x: x[0], reverse=True)
            )
            logging.info(
                f"Best Parameters: {sorted_dict[next(iter(sorted_dict))]}"
            )

    if training:
        await run_training()
    else:
        await run_once()
