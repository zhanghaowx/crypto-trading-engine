"""
CLI interface for jolteon project.
"""
import asyncio
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


async def train():
    symbol = "BTC/USD"
    replay_start = datetime(
        2024, 1, 16, hour=0, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 16, hour=23, minute=59, second=0, tzinfo=pytz.utc
    )

    # Start Hyper Parameters Setup
    train_result = dict[float, dict]()
    for minute in range(1, 6):
        for bull_flag_pct in np.arange(0.001, 0.002, 0.0002):
            for consolidate_pct in np.arange(0.1, 0.301, 0.1):
                for reward_ratio in np.arange(2.0, 5.0, 0.5):
                    # Start Training
                    strategy_params = Parameters(
                        max_number_of_recent_candlesticks=10,
                        target_reward_risk_ratio=reward_ratio,
                    )
                    bull_flag_params = BullFlagParameters(
                        extreme_bullish_return_pct=bull_flag_pct,
                        consolidation_period_threshold_cutoff=consolidate_pct,
                    )
                    app = Application(
                        symbol,
                        candlestick_interval_in_seconds=minute * 60,
                        database_name=f"/tmp/train_{len(train_result)}.sqlite",
                        logfile_name=f"/tmp/train_{len(train_result)}.log",
                        strategy_params=strategy_params,
                        bull_flag_params=bull_flag_params,
                    )
                    pnl = await app.run_replay(replay_start, replay_end)
                    app.disconnect_signals()

                    train_result[pnl] = {
                        "strategy_params": strategy_params,
                        "bull_flag_params": bull_flag_params,
                        "candlestick_interval_in_seconds": minute * 60,
                    }
                    print(
                        f"Training PnL: {pnl}, Parameters: {train_result[pnl]}"
                    )
                    logging.info(
                        f"Training PnL: {pnl}, Parameters: {train_result[pnl]}"
                    )

                    # Prepare for next iteration
                    time_manager().force_reset()
                    # End of one run

    if len(train_result) == 0:
        logging.warning("No best parameters found. Exiting...")
    else:
        sorted_dict = dict(
            sorted(train_result.items(), key=lambda x: x[0], reverse=True)
        )
        print(f"Best Parameters: {sorted_dict[next(iter(sorted_dict))]}")
        logging.info(
            f"Best Parameters: {sorted_dict[next(iter(sorted_dict))]}"
        )


if __name__ == "__main__":
    asyncio.run(train())
