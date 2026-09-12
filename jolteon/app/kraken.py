"""
Application interface for Jolteon
"""

import logging
from datetime import datetime

import pytz

from jolteon.app.base import ApplicationBase
from jolteon.engine.core.parameter.parameter_service import IParameterService
from jolteon.engine.execution.kraken.execution_service import ExecutionService
from jolteon.engine.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.historical_feed import HistoricalFeed
from jolteon.engine.market_data.kraken.data_source import (
    KrakenHistoricalDataSource,
)
from jolteon.engine.market_data.kraken.public_feed import PublicFeed
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)


class KrakenApplication(ApplicationBase):
    def __init__(
        self,
        symbol: str,
        use_mock_execution: bool = True,
        database_name="/tmp/jolteon.sqlite",
        logfile_name="/tmp/jolteon.log",
        strategy: object = None,
        fair_price_model: IFairPriceModel | None = None,
        parameter_service: IParameterService | None = None,
    ):
        print(f"Using {type(self).__name__}")
        super().__init__(
            symbol=symbol.replace("-", "/"),
            database_name=database_name,
            logfile_name=logfile_name,
            strategy=strategy,
            fair_price_model=fair_price_model,
            parameter_service=parameter_service,
        )
        if use_mock_execution:
            super().use_execution_service(MockExecutionService())
        else:
            super().use_execution_service(ExecutionService())

    async def start(self):
        super().use_market_data_service(PublicFeed())

        logging.info(f"Running {self._symbol} live")
        print(f"Running {self._symbol} live")

        return await super().run_start()

    async def run_replay(self, start: datetime, end: datetime):
        super().use_market_data_service(
            HistoricalFeed(KrakenHistoricalDataSource())
        )

        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        print(f"Replaying {self._symbol} from {start} to {end}")
        now = datetime.now(tz=pytz.utc)
        return await super().run_start(start, min(now, end))
