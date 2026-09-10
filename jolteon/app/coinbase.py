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
from jolteon.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)


class CoinbaseApplication(ApplicationBase):
    def __init__(
        self,
        symbol: str,
        use_mock_execution: bool = True,
        database_name="/tmp/jolteon.sqlite",
        logfile_name="/tmp/jolteon.log",
        strategy: object = None,
        fair_price_model: IFairPriceModel | None = None,
    ):
        print(f"Using {type(self).__name__}")
        super().__init__(
            symbol=symbol,
            database_name=database_name,
            logfile_name=logfile_name,
            strategy=strategy,
            fair_price_model=fair_price_model,
        )
        if use_mock_execution:
            super().use_execution_service(MockExecutionService())
        else:
            super().use_execution_service(MockExecutionService())

    async def start(self):
        logging.info(f"Running {self._symbol}")

        print(type(super()))
        super().use_market_data_service(PublicFeed())
        return await super().run_start()

    async def run_replay(self, start: datetime, end: datetime):
        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        super().use_market_data_service(
            HistoricalFeed(CoinbaseHistoricalDataSource())
        )
        now = datetime.now(tz=pytz.utc)
        return await super().run_start(start, min(now, end))
