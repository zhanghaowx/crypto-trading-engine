"""
Application interface for Jolteon
"""
import logging
from datetime import datetime

import pytz

from jolteon.app.base import ApplicationBase
from jolteon.execution.coinbase.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.coinbase.data_source import (
    CoinbaseHistoricalDataSource,
)
from jolteon.market_data.coinbase.public_feed import PublicFeed
from jolteon.market_data.historical_feed import HistoricalFeed
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)


class CoinbaseApplication(ApplicationBase):
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
            symbol=symbol,
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
            super().use_execution_service(MockExecutionService())

    async def start(self):
        logging.info(f"Running {self._symbol}")

        print(type(super()))
        interval_in_seconds = self._candlestick_interval_in_seconds
        super().use_market_data_service(
            PublicFeed(candlestick_interval_in_seconds=interval_in_seconds)
        )
        return await super().run_start()

    async def run_replay(self, start: datetime, end: datetime):
        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        super().use_market_data_service(
            HistoricalFeed(
                CoinbaseHistoricalDataSource(),
                self._candlestick_interval_in_seconds,
            )
        )
        now = datetime.now(tz=pytz.utc)
        return await super().run_start(start, min(now, end))
