"""
Application interface for Jolteon
"""
import logging
from datetime import datetime

from blinker import signal

from jolteon.core.event.signal_connector import SignalConnector
from jolteon.core.time.time_manager import time_manager
from jolteon.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.kraken.historical_feed import HistoricalFeed
from jolteon.market_data.kraken.public_feed import PublicFeed
from jolteon.position.position_manager import PositionManager
from jolteon.risk_limit.order_frequency_limit import OrderFrequencyLimit
from jolteon.strategy.bull_flag.parameters import Parameters
from jolteon.strategy.bull_flag.strategy import BullFlagStrategy
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)
from jolteon.strategy.core.patterns.bull_flag.recognizer import (
    BullFlagRecognizer,
)
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)
from jolteon.strategy.core.patterns.shooting_star.recognizer import (
    ShootingStarRecognizer,
)


class Application:
    def __init__(
        self,
        symbol: str,
        database_name="/tmp/crypto.sqlite",
        logfile_name="/tmp/crypto.log",
        candlestick_interval_in_seconds=60,
        bull_flag_params=BullFlagParameters(),
        shooting_star_params=ShootingStarParameters(),
        strategy_params=Parameters(),
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
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
        )

        # Market Data Setup: Historical Feed
        self._md_historical = HistoricalFeed(
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
        )

        # Strategy Setup
        self._strategy = BullFlagStrategy(
            symbol,
            risk_limits=[
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60)
            ],
            parameters=strategy_params,
        )

        # Execution Setup
        self._exec_service = MockExecutionService()

        # Position Manager Setup
        self._position_manager = PositionManager()

        self.bull_flag_recognizer = BullFlagRecognizer(params=bull_flag_params)
        self.shooting_star_recognizer = ShootingStarRecognizer(
            params=shooting_star_params
        )

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
            self._md_live.events.candlestick,
            self.shooting_star_recognizer.on_candlestick,
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
            self._md_historical.events.candlestick,
            self.shooting_star_recognizer.on_candlestick,
        )
        self._signal_connector.connect(
            self.bull_flag_recognizer.bull_flag_signal,
            self._strategy.on_bull_flag_pattern,
        )
        self._signal_connector.connect(
            self.shooting_star_recognizer.shooting_star_signal,
            self._strategy.on_shooting_star_pattern,
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
        self._signal_connector.connect(signal("heartbeat"))

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
        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        await self._md_historical.connect(
            self._symbol, start, min(time_manager().now(), end)
        )
        return self._position_manager.pnl

    async def run(self):
        logging.info(f"Running {self._symbol}")
        try:
            await self._md_live.connect([self._symbol])
        except Exception as e:
            logging.error(f"Error: {e}")
