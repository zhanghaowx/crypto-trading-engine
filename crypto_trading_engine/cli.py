"""
CLI interface for crypto_trading_engine project.
"""
import logging

from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    CoinbasePublicFeed,
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

    # Marketdata Setup
    md = CoinbasePublicFeed(
        env=CoinbaseEnvironment.PRODUCTION, candlestick_interval_in_seconds=60
    )
    md_connection = md.connect(["ETH-USD"])

    # Strategy Setup
    strategy = BullFlagStrategy(min_return_of_active_candlesticks=0.0001)
    md.events.candlestick.connect(strategy.on_candlestick)

    await md_connection
