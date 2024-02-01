import asyncio
import logging
import threading
from datetime import datetime

import pytz
from blinker import signal

from jolteon.core.event.signal_connector import SignalConnector
from jolteon.core.logging.logger import setup_global_logger
from jolteon.market_data.data_source import DatabaseDataSource
from jolteon.market_data.historical_feed import HistoricalFeed
from jolteon.position.position_manager import PositionManager
from jolteon.risk_limit.order_frequency_limit import OrderFrequencyLimit
from jolteon.strategy.bull_trend_rider.strategy import BullFlagStrategy
from jolteon.strategy.core.patterns.bull_flag.recognizer import (
    BullFlagRecognizer,
)
from jolteon.strategy.core.patterns.shooting_star.recognizer import (
    ShootingStarRecognizer,
)


class ApplicationBase:
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
        setup_global_logger(log_level=logging.DEBUG, logfile_name=logfile_name)

        self._signal_connector = SignalConnector(
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
        self._strategy = BullFlagStrategy(
            symbol,
            risk_limits=[
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60 * 2),
                OrderFrequencyLimit(number_of_orders=2, in_seconds=60 * 10),
            ],
            parameters=strategy_params,
        )

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
        self._signal_connector.close()

    def _connect_signals(self):
        # MD
        assert self._md is not None
        self._signal_connector.connect(
            self._md.events.candlestick, self._strategy.on_candlestick
        )
        self._signal_connector.connect(
            self._md.events.candlestick,
            self._bull_flag_recognizer.on_candlestick,
        )
        self._signal_connector.connect(
            self._md.events.candlestick,
            self._shooting_star_recognizer.on_candlestick,
        )
        self._signal_connector.connect(self._md.events.market_trade)

        # Execution
        assert self._exec_service is not None
        self._signal_connector.connect(
            self._strategy.order_event, self._exec_service.on_order
        )
        self._signal_connector.connect(
            self._strategy.order_event, self._exec_service.on_order
        )
        self._signal_connector.connect(
            self._exec_service.order_fill_event, self._strategy.on_fill
        )
        self._signal_connector.connect(
            self._exec_service.order_fill_event,
            self._position_manager.on_fill,
        )
        # Strategy
        self._signal_connector.connect(
            self._bull_flag_recognizer.bull_flag_signal,
            self._strategy.on_bull_flag_pattern,
        )
        self._signal_connector.connect(
            self._shooting_star_recognizer.shooting_star_signal,
            self._strategy.on_shooting_star_pattern,
        )
        self._signal_connector.connect(self._strategy.opportunity_event)
        self._signal_connector.connect(self._strategy.trade_result_event)
        self._signal_connector.connect(signal("heartbeat"))

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
