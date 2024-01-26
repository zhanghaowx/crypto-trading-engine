"""
Application interface for Jolteon
"""
import logging
from datetime import datetime

import pytz

from jolteon.app.base import ApplicationBase
from jolteon.execution.kraken.execution_service import ExecutionService
from jolteon.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.historical_feed import HistoricalFeed
from jolteon.market_data.kraken.data_source import KrakenHistoricalDataSource
from jolteon.market_data.kraken.public_feed import PublicFeed
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)


class KrakenApplication(ApplicationBase):
    def __init__(
        self,
        symbol: str,
        use_mock_execution: bool = True,
        database_name="/tmp/jolteon.sqlite",
        logfile_name="/tmp/jolteon.log",
        candlestick_interval_in_seconds=60,
        bull_flag_params=BullFlagParameters(),
        shooting_star_params=ShootingStarParameters(),
        strategy_params=StrategyParameters(),
    ):
        print(f"Using {type(self).__name__}")
        super().__init__(
            symbol=symbol.replace("-", "/"),
            database_name=database_name,
            logfile_name=logfile_name,
            candlestick_interval_in_seconds=candlestick_interval_in_seconds,
            bull_flag_params=bull_flag_params,
            shooting_star_params=shooting_star_params,
            strategy_params=strategy_params,
        )
        if use_mock_execution:
            super().use_execution_service(MockExecutionService())
        else:
            super().use_execution_service(ExecutionService())

    async def start(self):
        super().use_market_data_service(
            PublicFeed(self._candlestick_interval_in_seconds)
        )

        logging.info(f"Running {self._symbol} live")
        print(f"Running {self._symbol} live")

        # When running in live mode, we want to be able to monitor via checking
        # updates in database
        self._signal_connector.enable_auto_save(auto_save_interval=30)
        return await super().run_start()

    async def run_replay(self, start: datetime, end: datetime):
        super().use_market_data_service(
            HistoricalFeed(
                KrakenHistoricalDataSource(),
                self._candlestick_interval_in_seconds,
            )
        )

        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        print(f"Replaying {self._symbol} from {start} to {end}")
        now = datetime.now(tz=pytz.utc)
        return await super().run_start(start, min(now, end))
