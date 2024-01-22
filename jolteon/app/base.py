import logging
from datetime import datetime
from typing import Type

import pytz
from blinker import signal

from jolteon.core.event.signal_connector import SignalConnector
from jolteon.position.position_manager import PositionManager
from jolteon.risk_limit.order_frequency_limit import OrderFrequencyLimit
from jolteon.strategy.bull_trend_rider.strategy import BullFlagStrategy
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
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


class ApplicationBase:
    def __init__(
        self,
        symbol: str,
        database_name="/tmp/jolteon.sqlite",
        logfile_name="/tmp/jolteon.log",
        bull_flag_params=BullFlagParameters(),
        shooting_star_params=ShootingStarParameters(),
        strategy_params=StrategyParameters(),
    ):
        """
        Connects different components to build the trading engine. It supports
        one symbol and one strategy.
        """
        self._symbol = symbol
        print(f"Using {self._symbol}")

        # Data Dumping Setup
        logging.basicConfig(
            filename=logfile_name,
            filemode="w",
            format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
            level=logging.INFO,
        )
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
                OrderFrequencyLimit(number_of_orders=1, in_seconds=60)
            ],
            parameters=strategy_params,
        )

        # Per Exchange Setup (Decided Later)
        self._exec_service: object = None
        self._md: object = None

    def __del__(self):
        self.stop()

    def use_execution_service(self, ExecutionServiceClass: Type):
        print(f"Using {ExecutionServiceClass.__name__}")
        self._exec_service = ExecutionServiceClass()
        return self

    def use_market_data_service(
        self, MarketDataClass: Type, candlestick_interval_in_seconds: int = 60
    ):
        print(f"Using {MarketDataClass.__name__}")
        self._md = MarketDataClass(
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
        )
        return self

    async def run(self):
        logging.info(f"Running {self._symbol}")
        self._connect_signals()

        # Start receiving market data
        try:
            await self._md.connect([self._symbol])
        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)

        return self._position_manager.pnl

    async def run_replay(self, start: datetime, end: datetime):
        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        self._connect_signals()

        # Start receiving market data
        await self._md.connect(  # type: ignore[attr-defined]
            self._symbol, start, min(datetime.now(tz=pytz.utc), end)
        )
        return self._position_manager.pnl

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
        self._signal_connector.connect(self._md.events.matches)

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
