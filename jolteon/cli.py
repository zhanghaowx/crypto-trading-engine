"""
CLI interface for jolteon project.
"""
import logging
import signal
import sys
from datetime import datetime

import numpy as np
import pytz

from jolteon.app import Application
from jolteon.core.time.time_manager import time_manager
from jolteon.strategy.bull_flag.parameters import Parameters


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main(training: bool = False):
    replay_start = datetime(
        2024, 1, 14, hour=0, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 14, hour=23, minute=59, second=0, tzinfo=pytz.utc
    )

    async def run_once(parameters: Parameters = Parameters()):
        app = Application(
            "ETH-USD",
            candlestick_interval_in_seconds=60,
            strategy_parameters=parameters,
        )

        pnl = await app.run_replay(replay_start, replay_end)

        pnl_report = f"PnL: {pnl}, Parameters: {parameters}"
        logging.info(pnl_report)
        print(pnl_report)

        # Prepare for next iteration
        time_manager().force_reset()

        return pnl

    async def run_training():
        result = dict[float, Parameters]()

        # Start Training
        for consolidation_threshold in np.arange(0.1, 0.3, 0.05):
            parameters = Parameters(
                max_number_of_recent_candlesticks=10,
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
