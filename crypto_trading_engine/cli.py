"""
CLI interface for crypto_trading_engine project.
"""
import logging
import os
import signal
import sys
from datetime import datetime, timedelta

import pytz

from crypto_trading_engine.core.event.signal_connector import SignalConnector
from crypto_trading_engine.execution.coinbase.execution_service import (
    MockExecutionService,
)
from crypto_trading_engine.market_data.coinbase.historical_feed import (
    HistoricalFeed,
)
from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    PublicFeed,
)
from crypto_trading_engine.position.position_manager import PositionManager
from crypto_trading_engine.risk_limit.order_frequency_limit import (
    OrderFrequencyLimit,
)
from crypto_trading_engine.strategy.bull_flag.bull_flag_strategy import (
    BullFlagStrategy,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main():  # pragma: no cover
    """
    Connects different components, starts the engine and runs a strategy.
    """

    source_directory = os.path.dirname(os.path.dirname(__file__))
    connector = SignalConnector(
        database_name=f"{source_directory}/analysis/crypto.sqlite3"
    )

    # Logging setup
    logging.basicConfig(
        filename=f"{source_directory}/analysis/crypto.log",
        filemode="w",
        format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
        level=logging.INFO,
    )

    # Market Data Setup

    # Live
    md_live = PublicFeed(
        env=CoinbaseEnvironment.PRODUCTION, candlestick_interval_in_seconds=60
    )
    _ = md_live  # Variable is assigned but not used intentionally

    # Historical
    end_time = datetime(
        2024, 1, 11, hour=23, minute=30, second=0, tzinfo=pytz.utc
    )
    md_historical = HistoricalFeed(
        start_time=end_time - timedelta(minutes=300),
        end_time=end_time,
    )
    _ = md_historical  # Variable is assigned but not used intentionally

    # Strategy Setup
    strategy = BullFlagStrategy(
        "ETH-USD",
        risk_limits=[OrderFrequencyLimit(number_of_orders=1, in_seconds=60)],
        parameters=Parameters(
            max_number_of_recent_candlesticks=10,
        ),
    )

    # Execution Setup
    exec_service = MockExecutionService()

    # Position Manager Setup
    position_manager = PositionManager()

    # Wire Events
    # connector.connect(md.events.ticker)
    # connector.connect(md.events.matches)
    # connector.connect(md.events.channel_heartbeat)
    connector.connect(
        md_historical.events.candlestick, strategy.on_candlestick
    )
    connector.connect(strategy.order_event, exec_service.on_order)
    connector.connect(exec_service.order_fill_event, strategy.on_fill)
    connector.connect(exec_service.order_fill_event, position_manager.on_fill)

    # await md_live.connect(["ETH-USD"])
    await md_historical.connect("ETH-USD")
