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
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)


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

    async def run_once(app: Application):
        pnl = await app.run_replay(replay_start, replay_end)

        pnl_report = f"PnL: {pnl}"
        logging.info(pnl_report)
        print(pnl_report)

        # Prepare for next iteration
        time_manager().force_reset()

        return pnl

    async def run_training():
        result = dict[float, dict]()

        # Start Training
        for extreme_bullish_return_pct in np.arange(0.001, 0.002, 0.0001):
            for consolidation_threshold in np.arange(0.1, 0.301, 0.05):
                strategy_params = Parameters(
                    max_number_of_recent_candlesticks=10,
                    consolidation_period_threshold=consolidation_threshold,
                )
                bull_flag_params = BullFlagParameters(
                    extreme_bullish_return_pct=extreme_bullish_return_pct
                )

                pnl = await run_once(
                    Application(
                        "ETH-USD",
                        strategy_params=strategy_params,
                        bull_flag_params=bull_flag_params,
                    )
                )

                result[pnl] = {
                    "strategy_params": strategy_params,
                    "bull_flag_params": bull_flag_params,
                }

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
        await run_once(Application("ETH-USD"))
