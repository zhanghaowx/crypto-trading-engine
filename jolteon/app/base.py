import asyncio
import logging
import threading
from datetime import datetime

import pytz

from jolteon.core.event.signal_manager import SignalManager
from jolteon.core.event.signal_recorder import SignalRecorder
from jolteon.core.logging.logger import setup_global_logger
from jolteon.market_data.core.indicator.rsi import RSICalculator
from jolteon.market_data.data_source import DatabaseDataSource
from jolteon.market_data.historical_feed import HistoricalFeed
from jolteon.position.position_manager import PositionManager
from jolteon.risk_limit.order_frequency_limit import OrderFrequencyLimit
from jolteon.strategy.bull_trend_rider.strategy import BullTrendRiderStrategy
from jolteon.strategy.core.patterns.bull_flag.recognizer import (
    BullFlagRecognizer,
)
from jolteon.strategy.core.patterns.shooting_star.recognizer import (
    ShootingStarRecognizer,
)


class ApplicationBase(SignalManager):
    THREAD_ENABLED: bool = True
    THREAD_SYNC_INTERVAL: float = 10

    def __init__(
        self,
        symbol: str,
        database_name,
        logfile_name,
        candlestick_interval_in_seconds,
        bull_flag_params,
        shooting_star_params,
        strategy_params,
    ):
        """
        Connects different components to build the trading engine. It supports
        one symbol and one strategy.
        """
        self._symbol = symbol
        self._candlestick_interval_in_seconds = candlestick_interval_in_seconds

        # Data Dumping Setup
        setup_global_logger(
            log_level=logging.DEBUG,
            logfile_name=logfile_name,
            logfile_db=database_name,
        )

        self._signal_recorder = SignalRecorder(
            database_name=database_name,
        )

        # Position Manager Setup
        self._position_manager = PositionManager()

        # Strategy Setup
        self._bull_flag_recognizer = BullFlagRecognizer(
            params=bull_flag_params
        )
        self._shooting_star_recognizer = ShootingStarRecognizer(
            params=shooting_star_params
        )
        self._strategy = BullTrendRiderStrategy(
            symbol,
            risk_limits=[
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60 * 2),
                OrderFrequencyLimit(number_of_orders=2, in_seconds=60 * 10),
            ],
            parameters=strategy_params,
        )

        # Indicators
        self._rsi_calculator = RSICalculator()

        # Per Exchange Setup (Decided Later)
        self._exec_service: object = None
        self._md: object = None

    def use_execution_service(self, service: object):
        print(f"Using {type(service).__name__}")
        self._exec_service = service
        return self

    def use_market_data_service(self, market_data: object):
        print(f"Using {type(market_data).__name__}")
        self._md = market_data
        return self

    async def run_start(self, *args):
        self._connect_signals()

        if ApplicationBase.THREAD_ENABLED:
            # Start receiving market data
            md_thread = self._start_thread(
                "MD", self._md.connect(self._symbol, *args)
            )

            # Start other asyncio tasks (heartbeating, ..., etc)
            async def main_asyncio_tasks() -> None:
                while md_thread.is_alive():
                    await asyncio.sleep(self.THREAD_SYNC_INTERVAL)

            await main_asyncio_tasks()
        else:
            await self._md.connect(self._symbol, *args)

        for symbol, position in self._position_manager.positions.items():
            print(f"{symbol}: {position.volume}")

        self.stop()
        return self._position_manager.pnl

    async def run_local_replay(self, db: str):
        data_source = DatabaseDataSource(db)
        start = data_source.start_time()
        end = data_source.end_time()

        self.use_market_data_service(
            HistoricalFeed(
                data_source,
                self._candlestick_interval_in_seconds,
            )
        )

        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        print(f"Replaying {self._symbol} from {start} to {end}")
        now = datetime.now(tz=pytz.utc)
        return await self.run_start(start, min(now, end))

    def stop(self):
        # Disconnect every blinker signal from its receivers
        self._disconnect_signals()

    def _connect_signals(self):
        self.connect_all()
        self._signal_recorder.start_recording()

    def _disconnect_signals(self):
        self.disconnect_all()
        self._signal_recorder.stop_recording()

    @staticmethod
    def _start_thread(name: str, task):
        def run_task():
            # Create a new event loop for the thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the first async task with arguments in the event loop
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass  # Ignore CancelledError on cleanup
            except Exception as e:
                logging.error(f"{name} got exception: {e}", exc_info=True)
                raise e

            loop.close()

        thread = threading.Thread(
            name=name,
            target=run_task,
        )
        thread.start()

        return thread
