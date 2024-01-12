"""
CLI interface for crypto_trading_engine project.
"""
import logging
import signal
import sys

from crypto_trading_engine.core.eventing.signal_connector import (
    SignalConnector,
)
from crypto_trading_engine.execution.coinbase.execution_service import (
    MockExecutionService,
)
from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    CoinbasePublicFeed,
)
from crypto_trading_engine.position.position_manager import PositionManager
from crypto_trading_engine.risk_limit.order_frequency_limit import (
    OrderFrequencyLimit,
)
from crypto_trading_engine.strategy.bull_flag_strategy import BullFlagStrategy


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

    connector = SignalConnector()

    # Logging setup
    logging.basicConfig(
        filename="crypto.log",
        filemode="w",
        format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
        level=logging.INFO,
    )

    # Market Data Setup
    md = CoinbasePublicFeed(
        env=CoinbaseEnvironment.PRODUCTION, candlestick_interval_in_seconds=60
    )
    md_connection = md.connect(["ETH-USD"])

    # Strategy Setup
    strategy = BullFlagStrategy(
        "ETH-USD",
        risk_limits=[OrderFrequencyLimit(number_of_orders=1, in_seconds=60)],
        max_number_of_recent_candlesticks=3,
        min_number_of_bearish_candlesticks=1,
        min_return_of_active_candlesticks=0.0001,
    )

    # Execution Setup
    exec_service = MockExecutionService()

    # Position Manager Setup
    position_manager = PositionManager()

    # Wire Events
    connector.connect(md.events.ticker)
    connector.connect(md.events.matches)
    connector.connect(md.events.channel_heartbeat)
    connector.connect(md.events.candlestick, strategy.on_candlestick)
    connector.connect(strategy.order_event, exec_service.on_order)
    connector.connect(exec_service.order_fill_event, strategy.on_fill)
    connector.connect(exec_service.order_fill_event, position_manager.on_fill)

    await md_connection
