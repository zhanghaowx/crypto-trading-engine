"""
Application interface for Jolteon
"""
from datetime import datetime

from jolteon.app.base import ApplicationBase
from jolteon.execution.kraken.execution_service import ExecutionService
from jolteon.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.kraken.historical_feed import HistoricalFeed
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
        super().__init__(
            symbol=symbol.replace("-", "/"),
            database_name=database_name,
            logfile_name=logfile_name,
            bull_flag_params=bull_flag_params,
            shooting_star_params=shooting_star_params,
            strategy_params=strategy_params,
        )
        if use_mock_execution:
            super().use_execution_service(MockExecutionService)
        else:
            super().use_execution_service(ExecutionService)

        self._candlestick_interval_in_seconds = candlestick_interval_in_seconds

    async def run(self):
        super().use_market_data_service(
            PublicFeed, self._candlestick_interval_in_seconds
        )
        await super().run()

    async def run_replay(self, start: datetime, end: datetime):
        super().use_market_data_service(
            HistoricalFeed, self._candlestick_interval_in_seconds
        )
        return await super().run_replay(start, end)
