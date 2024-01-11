"""
CLI interface for crypto_trading_engine project.
"""
import logging

from crypto_trading_engine.execution.coinbase.execution_service import (
    MockExecutionService,
)
from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    CoinbasePublicFeed,
)
from crypto_trading_engine.risk_limit.order_frequency_limit import (
    OrderFrequencyLimit,
)
from crypto_trading_engine.strategy.bull_flag_strategy import BullFlagStrategy


async def main():  # pragma: no cover
    """
    Connects different components, starts the engine and runs a strategy.
    """

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
    md.events.candlestick.connect(strategy.on_candlestick)

    # Execution Setup
    execution_service = MockExecutionService()
    strategy.order_event.connect(execution_service.on_order)
    execution_service.order_fill_event.connect(strategy.on_fill)

    await md_connection
