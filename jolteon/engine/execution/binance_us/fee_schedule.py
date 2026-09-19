from dataclasses import dataclass

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_specification import parameter


@dataclass(frozen=True)
class FeeTier:
    minimum_volume: float
    maker_rate: float
    taker_rate: float


# https://www.binance.us/fees
SPOT_TIERS = (
    FeeTier(0.0, 0.0000, 0.000200),
    FeeTier(500_000_000.0, 0.0000, 0.000100),
)


@dataclass(frozen=True)
class BinanceUsFeeSchedule(FeeSchedule):
    """
    Binance.US's published spot fee schedule, per
    https://www.binance.us/fees. A maker pays nothing, on every pair at
    every volume, and a taker pays a rate that halves once the account
    has traded enough over the last 30 days.

    Two published discounts are not modelled, so an account entitled to
    either is charged too much here rather than too little: paying fees
    in BNB takes 5% off, and BNB/USD is charged from a cheaper schedule
    than every other pair.
    """

    thirty_day_volume: float = parameter(
        0.0,
        minimum=0.0,
        maximum=1_000_000_000_000.0,
        step=1_000_000.0,
        number_format="%.0f",
        unit="USD",
        description=(
            "Notional traded over the last 30 days, which is what "
            "Binance.US picks the taker rate from."
        ),
    )

    @property
    def maker_rate(self) -> float:
        return self._tier.maker_rate

    @property
    def taker_rate(self) -> float:
        return self._tier.taker_rate

    @property
    def _tier(self) -> FeeTier:
        return next(
            tier
            for tier in reversed(SPOT_TIERS)
            if self.thirty_day_volume >= tier.minimum_volume
        )
