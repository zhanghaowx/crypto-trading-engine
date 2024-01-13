"""
Application interface for Jolteon
"""
import logging
import os
from datetime import datetime, timedelta

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


class Application:
    SOURCE_DIRECTORY = os.path.dirname(os.path.dirname(__file__))

    def __init__(
        self,
        symbol: str,
        database_name=f"{SOURCE_DIRECTORY}/analysis/crypto.sqlite",
        logfile_name=f"{SOURCE_DIRECTORY}/analysis/crypto.log",
    ):
        """
        Connects different components, starts the engine.

        Args:
            symbol:
            database_name:
            logfile_name:
        """
        self._symbol = symbol

        # Data Dumping Setup
        self._signal_connector = SignalConnector(
            database_name=database_name,
        )
        logging.basicConfig(
            filename=logfile_name,
            filemode="w",
            format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
            level=logging.INFO,
        )

        # Market Data Setup

        # Market Data Setup: Live Feed
        self._md_live = PublicFeed(
            env=CoinbaseEnvironment.PRODUCTION,
            candlestick_interval_in_seconds=60,
        )

        # Market Data Setup: Historical Feed
        self._md_historical = HistoricalFeed()

        # Strategy Setup
        self._strategy = BullFlagStrategy(
            symbol,
            risk_limits=[
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60)
            ],
            parameters=Parameters(
                max_number_of_recent_candlesticks=10,
            ),
        )

        # Execution Setup
        self._exec_service = MockExecutionService()

        # Position Manager Setup
        self._position_manager = PositionManager()

        # Wire Events
        self._signal_connector.connect(
            self._md_live.events.candlestick, self._strategy.on_candlestick
        )
        self._signal_connector.connect(
            self._md_historical.events.candlestick,
            self._strategy.on_candlestick,
        )
        self._signal_connector.connect(
            self._strategy.order_event, self._exec_service.on_order
        )
        self._signal_connector.connect(
            self._exec_service.order_fill_event, self._strategy.on_fill
        )
        self._signal_connector.connect(
            self._exec_service.order_fill_event, self._position_manager.on_fill
        )

    async def run_replay(self, start: datetime, end: datetime):
        def generate_time_ranges(interval_minutes: int):
            result_time_ranges = []

            current_time = start
            while current_time < end:
                next_time = current_time + timedelta(minutes=interval_minutes)
                result_time_ranges.append((current_time, next_time))
                current_time = next_time

            return result_time_ranges

        for start, end in generate_time_ranges(300):
            print(f"Replay for {start} - {end}")
            await self._md_historical.connect(self._symbol, start, end)

    async def run(self):
        await self._md_live.connect([self._symbol])
