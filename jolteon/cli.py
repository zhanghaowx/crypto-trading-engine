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


async def main(training: bool = False, replay: bool = False):
    assert (training and replay) or (
        not training
    ), "Training mode should only be used with replay mode"

    replay_start = datetime(
        2024, 1, 16, hour=0, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 16, hour=23, minute=59, second=0, tzinfo=pytz.utc
    )

    async def run_once(app: Application):
        if replay:
            pnl = await app.run_replay(replay_start, replay_end)
        else:
            pnl = await app.run()

        # Prepare for next iteration
        time_manager().force_reset()

        print(f"PnL: {pnl}")
        return pnl

    async def run_training(symbol: str):
        result = dict[float, dict]()

        # Start Training
        for minute in range(1, 6):
            for bull_flag_pct in np.arange(0.001, 0.002, 0.0001):
                for consolidation_pct in np.arange(0.1, 0.301, 0.05):
                    for reward_ratio in np.arange(2.0, 5.0, 0.2):
                        strategy_params = Parameters(
                            max_number_of_recent_candlesticks=10,
                            consolidation_period_threshold=consolidation_pct,
                            target_reward_risk_ratio=reward_ratio,
                        )
                        bull_flag_params = BullFlagParameters(
                            extreme_bullish_return_pct=bull_flag_pct
                        )

                        pnl = await run_once(
                            Application(
                                symbol,
                                candlestick_interval_in_seconds=minute * 60,
                                strategy_params=strategy_params,
                                bull_flag_params=bull_flag_params,
                            )
                        )

                        result[pnl] = {
                            "strategy_params": strategy_params,
                            "bull_flag_params": bull_flag_params,
                        }

                        logging.info(
                            f"Training PnL: {pnl}, Parameters: {result[pnl]}"
                        )

                        # End of one run

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
        await run_training("ETH/USD")
    else:
        await run_once(Application("ETH/USD"))
