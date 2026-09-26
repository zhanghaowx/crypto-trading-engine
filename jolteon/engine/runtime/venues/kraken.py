"""
Application interface for Jolteon
"""

import logging
from datetime import datetime

import pytz

from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.parameter.parameter_service import IParameterService
from jolteon.engine.execution.kraken.execution_service import ExecutionService
from jolteon.engine.execution.kraken.fee_schedule import KrakenFeeSchedule
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.kraken.data_source import (
    KrakenHistoricalDataSource,
)
from jolteon.engine.market_data.kraken.public_feed import PublicFeed
from jolteon.engine.runtime.engine_runtime import EngineRuntime
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)


class KrakenRuntime(EngineRuntime):
    def __init__(
        self,
        symbol: str,
        database_name: str,
        logfile_name: str,
        use_mock_execution: bool = True,
        strategy: object = None,
        fair_price_model: IFairPriceModel | None = None,
        parameter_service: IParameterService | None = None,
        health_monitor: HealthMonitor | None = None,
        run_id: str | None = None,
    ):
        print(f"Using {type(self).__name__}")
        super().__init__(
            symbol=symbol.replace("-", "/"),
            exchange="Kraken",
            database_name=database_name,
            logfile_name=logfile_name,
            strategy=strategy,
            fair_price_model=fair_price_model,
            parameter_service=parameter_service,
            health_monitor=health_monitor,
            run_id=run_id,
        )
        if use_mock_execution:
            super().use_execution_service(
                MockExecutionService(
                    KrakenFeeSchedule, health_monitor=self._health_monitor
                )
            )
        else:
            super().use_execution_service(
                ExecutionService(health_monitor=self._health_monitor)
            )

    async def start(self):
        super().use_market_data_service(
            PublicFeed(health_monitor=self._health_monitor)
        )

        logging.info(f"Running {self._symbol} live")
        print(f"Running {self._symbol} live")

        return await super().run_start()

    async def run_replay(self, start: datetime, end: datetime):
        end = min(datetime.now(tz=pytz.utc), end)
        super().use_recorded_market_data(
            KrakenHistoricalDataSource(), start, end
        )

        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        print(f"Replaying {self._symbol} from {start} to {end}")
        return await super().run_start(start, end)
