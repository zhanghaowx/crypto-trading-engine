"""
CLI interface for jolteon project.
"""
import asyncio
import gc
import logging
import signal
import sqlite3
import sys
import tempfile
from datetime import datetime

import numpy as np
import pandas as pd
import pytz

from jolteon.app.kraken import KrakenApplication as Application
from jolteon.core.time.time_manager import time_manager
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
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
        2024, 1, 20, hour=11, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 20, hour=11, minute=59, second=0, tzinfo=pytz.utc
    )

    # Start Hyper Parameters Setup
    train_result = list[dict]()
    for minute in range(1, 6):
        for bull_flag_pct in np.arange(0.001, 0.002, 0.0002):
            for consolidate_pct in np.arange(0.1, 0.301, 0.1):
                for reward_ratio in np.arange(2.0, 5.0, 0.5):
                    # Start Training
                    strategy_params = StrategyParameters(
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
                        database_name=f"{tempfile.gettempdir()}/"
                        f"train_{len(train_result)}.sqlite",
                        logfile_name=f"{tempfile.gettempdir()}/"
                        f"train_{len(train_result)}.log",
                        strategy_params=strategy_params,
                        bull_flag_params=bull_flag_params,
                    )
                    pnl = await app.run_replay(replay_start, replay_end)
                    app.stop()

                    result = {
                        **vars(strategy_params),
                        **vars(bull_flag_params),
                        "candlestick_interval_in_seconds": minute * 60,
                        "pnl": pnl,
                    }
                    train_result.append(result)

                    print(f"Training PnL: {pnl}, Parameters: {result}")
                    logging.info(f"Training PnL: {pnl}, Parameters: {result}")

                    # Prepare for next iteration

                    # Reset mock timestamp
                    time_manager().force_reset()

                    # Force garbage collection to destroy old Application
                    # instance
                    gc.collect()
                    # End of one run

    # Save result into a database
    conn = sqlite3.connect(f"{tempfile.gettempdir()}/train_result.sqlite")
    df = pd.DataFrame(train_result)
    df.to_sql(name="train_result", con=conn, if_exists="replace", index=False)


if __name__ == "__main__":
    asyncio.run(train())
