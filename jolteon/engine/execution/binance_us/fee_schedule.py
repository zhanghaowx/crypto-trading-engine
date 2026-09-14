from dataclasses import dataclass

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_specification import parameter


@dataclass(frozen=True)
class BinanceUsFeeSchedule(FeeSchedule):
    """Configurable advertised rates used by Binance.US paper sessions."""

    maker_rate_value: float = parameter(
        0.0,
        minimum=0.0,
        maximum=0.1,
        step=0.0001,
        number_format="%.4f",
        description="Maker fee as a fraction of filled notional.",
    )
    taker_rate_value: float = parameter(
        0.006,
        minimum=0.0,
        maximum=0.1,
        step=0.0001,
        number_format="%.4f",
        description="Taker fee as a fraction of filled notional.",
    )

    @property
    def maker_rate(self) -> float:
        return self.maker_rate_value

    @property
    def taker_rate(self) -> float:
        return self.taker_rate_value
