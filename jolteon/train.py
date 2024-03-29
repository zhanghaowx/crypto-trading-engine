"""
CLI interface for jolteon project.
"""
import argparse
import asyncio
import logging
import signal
import sqlite3
import sys
import tempfile

import numpy as np
import pandas as pd

from jolteon.core.market import Market
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
    parser = argparse.ArgumentParser(description="Jolteon Trading Engine")
    parser.add_argument("--train-db", help="Path to a SQLite database file")
    parser.add_argument("--exchange", help="Name of the exchange")

    # Access the arguments
    args = parser.parse_args()
    train_db = args.train_db

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

    symbol = "BTC/USD"

    # Start Hyper Parameters Setup
    train_result = list[dict]()
    for minute in range(1, 6):
        for bull_flag_pct in np.arange(0.0005, 0.00201, 0.0002):
            for consolidate_pct in np.arange(0.1, 0.301, 0.1):
                for reward_ratio in np.arange(2.0, 5.001, 0.5):
                    # Start Training
                    strategy_params = StrategyParameters(
                        max_number_of_recent_candlesticks=15,
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
                    pnl = await app.run_local_replay(db=train_db)

                    result = {
                        **vars(strategy_params),
                        **vars(bull_flag_params),
                        "candlestick_interval_in_seconds": minute * 60,
                        "pnl": pnl,
                    }
                    train_result.append(result)

                    print(f"Training PnL: {pnl}, Parameters: {result}")
                    logging.info(f"Training PnL: {pnl}, Parameters: {result}")

                    # End of one run

    # Save result into a database
    conn = sqlite3.connect(f"{tempfile.gettempdir()}/train_result.sqlite")
    df = pd.DataFrame(train_result)
    df.to_sql(name="train_result", con=conn, if_exists="replace", index=False)


if __name__ == "__main__":
    asyncio.run(train())
