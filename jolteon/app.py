"""
Application interface for Jolteon
"""
import logging
import os
from datetime import datetime, timedelta

from jolteon.core.event.signal_connector import SignalConnector
from jolteon.execution.coinbase.execution_service import MockExecutionService
from jolteon.market_data.coinbase.historical_feed import HistoricalFeed
from jolteon.market_data.coinbase.public_feed import (
    CoinbaseEnvironment,
    PublicFeed,
)
from jolteon.position.position_manager import PositionManager
from jolteon.risk_limit.order_frequency_limit import OrderFrequencyLimit
from jolteon.strategy.bull_flag.parameters import Parameters
from jolteon.strategy.bull_flag.strategy import BullFlagStrategy
from jolteon.strategy.core.patterns.bull_flag.recognizer import (
    BullFlagRecognizer,
)


class Application:
    SOURCE_DIRECTORY = os.path.dirname(os.path.dirname(__file__))

    def __init__(
        self,
        symbol: str,
        database_name=f"{SOURCE_DIRECTORY}/analysis/crypto.sqlite",
        logfile_name=f"{SOURCE_DIRECTORY}/analysis/crypto.log",
        candlestick_interval_in_seconds=60,
        strategy_parameters=Parameters(),
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
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
        )

        # Market Data Setup: Historical Feed
        self._md_historical = HistoricalFeed(
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
            replay_speed=6000,
        )

        # Strategy Setup
        self._strategy = BullFlagStrategy(
            symbol,
            risk_limits=[
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60)
            ],
            parameters=strategy_parameters,
        )

        # Execution Setup
        self._exec_service = MockExecutionService()

        # Position Manager Setup
        self._position_manager = PositionManager()

        self.bull_flag_recognizer = BullFlagRecognizer(params=Parameters())

        # Wire Events
        self.connect_signals()

    def __del__(self):
        self.disconnect_signals()

    def connect_signals(self):
        self._signal_connector.connect(
            self._md_live.events.candlestick, self._strategy.on_candlestick
        )
        self._signal_connector.connect(
            self._md_live.events.candlestick,
            self.bull_flag_recognizer.on_candlestick,
        )
        self._signal_connector.connect(
            self._md_historical.events.candlestick,
            self._strategy.on_candlestick,
        )
        self._signal_connector.connect(
            self._md_historical.events.candlestick,
            self.bull_flag_recognizer.on_candlestick,
        )
        self._signal_connector.connect(
            self.bull_flag_recognizer.bull_flag_signal,
            self._strategy.on_bull_flag_pattern,
        )
        self._signal_connector.connect(
            self._strategy.order_event, self._exec_service.on_order
        )
        self._signal_connector.connect(self._strategy.opportunity_event)
        self._signal_connector.connect(self._strategy.trade_result_event)
        self._signal_connector.connect(
            self._exec_service.order_fill_event, self._strategy.on_fill
        )
        self._signal_connector.connect(
            self._exec_service.order_fill_event, self._position_manager.on_fill
        )

    def disconnect_signals(self):
        self._md_live.events.candlestick.disconnect(
            self._strategy.on_candlestick
        )
        self._md_historical.events.candlestick.disconnect(
            self._strategy.on_candlestick
        )
        self._strategy.order_event.disconnect(self._exec_service.on_order)
        self._exec_service.order_fill_event.disconnect(self._strategy.on_fill)
        self._signal_connector.close()

    async def run_replay(self, start: datetime, end: datetime):
        def generate_time_ranges(interval_minutes: int):
            result_time_ranges = []

            current_time = start
            while current_time < end:
                next_time = current_time + timedelta(minutes=interval_minutes)
                result_time_ranges.append((current_time, next_time))
                current_time = next_time

            return result_time_ranges

        for period_start, period_end in generate_time_ranges(300):
            logging.info(
                f"Replay for {self._symbol}: "
                f"{period_start} - {min(period_end, end)}"
            )
            await self._md_historical.connect(
                self._symbol, period_start, min(period_end, end)
            )

        return self._position_manager.pnl

    async def run(self):
        await self._md_live.connect([self._symbol])
