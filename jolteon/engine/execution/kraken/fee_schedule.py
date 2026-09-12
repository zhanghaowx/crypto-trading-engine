from dataclasses import dataclass

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_specification import parameter


@dataclass(frozen=True)
class FeeTier:
    minimum_volume: float
    maker_rate: float
    taker_rate: float


# https://www.kraken.com/features/fee-schedule
CRYPTO_PAIR_TIERS = (
    FeeTier(0.0, 0.0040, 0.0080),
    FeeTier(2_500.0, 0.0030, 0.0060),
    FeeTier(10_000.0, 0.0022, 0.0038),
    FeeTier(25_000.0, 0.0020, 0.0035),
    FeeTier(50_000.0, 0.0015, 0.0030),
    FeeTier(100_000.0, 0.0012, 0.0025),
    FeeTier(250_000.0, 0.0010, 0.0022),
    FeeTier(500_000.0, 0.0008, 0.0020),
    FeeTier(1_000_000.0, 0.0006, 0.0018),
    FeeTier(2_500_000.0, 0.0004, 0.0015),
    FeeTier(5_000_000.0, 0.0002, 0.0012),
    FeeTier(10_000_000.0, 0.0000, 0.0010),
)

STABLECOIN_PAIR_TIERS = (
    FeeTier(0.0, 0.0020, 0.0020),
    FeeTier(50_000.0, 0.0016, 0.0016),
    FeeTier(100_000.0, 0.0012, 0.0012),
    FeeTier(250_000.0, 0.0008, 0.0008),
    FeeTier(500_000.0, 0.0004, 0.0004),
    FeeTier(1_000_000.0, 0.0002, 0.0002),
    FeeTier(10_000_000.0, 0.0000, 0.0001),
    FeeTier(100_000_000.0, 0.0000, 0.00001),
)


@dataclass(frozen=True)
class KrakenFeeSchedule(FeeSchedule):
    """
    Kraken's published spot fee schedule, per
    https://www.kraken.com/features/fee-schedule. Rates fall with 30 day
    traded volume, so an account trading above the base tier has to say
    so or it will price its quotes off fees it does not actually pay.

    Since July 2026 Kraken takes the best of that volume and the assets
    the account holds on the platform, per
    https://support.kraken.com/articles/cross-platform-fee-tier-changes.
    The assets route is not modelled, so an account that qualifies
    through it is charged too much here rather than too little.
    """

    thirty_day_volume: float = parameter(
        0.0,
        minimum=0.0,
        maximum=1_000_000_000.0,
        step=1_000.0,
        number_format="%.0f",
        unit="USD",
        description=(
            "Notional traded over the last 30 days, which is what "
            "Kraken picks the fee tier from."
        ),
    )
    stablecoin_pair: bool = parameter(
        False,
        description=(
            "Charge from Kraken's separate, cheaper schedule for "
            "stablecoin, pegged token and FX pairs."
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
        tiers = (
            STABLECOIN_PAIR_TIERS
            if self.stablecoin_pair
            else CRYPTO_PAIR_TIERS
        )
        return next(
            tier
            for tier in reversed(tiers)
            if self.thirty_day_volume >= tier.minimum_volume
        )
