import logging

from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.parameter.parameter_service import IParameterService
from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.binance_us.public_feed import PublicFeed
from jolteon.engine.runtime.engine_runtime import EngineRuntime
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)


class BinanceUsRuntime(EngineRuntime):
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
    ):
        if not use_mock_execution:
            raise NotImplementedError(
                "Live Binance.US execution is not implemented; use --paper"
            )
        super().__init__(
            symbol=symbol.replace("-", "/").upper(),
            exchange="Binance.US",
            database_name=database_name,
            logfile_name=logfile_name,
            strategy=strategy,
            fair_price_model=fair_price_model,
            parameter_service=parameter_service,
            health_monitor=health_monitor,
        )
        super().use_execution_service(
            MockExecutionService(
                BinanceUsFeeSchedule, health_monitor=self._health_monitor
            )
        )

    async def start(self):
        super().use_market_data_service(
            PublicFeed(health_monitor=self._health_monitor)
        )
        logging.info("Running %s on Binance.US", self._symbol)
        return await super().run_start()

    async def run_replay(self, start, end):
        raise NotImplementedError(
            "Binance.US remote historical replay is not implemented"
        )
