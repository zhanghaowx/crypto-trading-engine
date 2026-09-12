from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class FeeSchedule(ParameterGroup):
    """
    What a venue charges to trade, as a fraction of the notional filled.
    The maker rate applies to an order that rested on the book before it
    filled, the taker rate to one that crossed to fill immediately.

    Defaults are Kraken's base tier, per
    https://www.kraken.com/features/fee-schedule. The rates fall with 30
    day volume, so an account trading above base tier needs to say so.
    """

    maker_rate: float = parameter(
        0.0025,
        minimum=0.0,
        maximum=0.1,
        step=0.0001,
        number_format="%.4f",
        description="Charged on an order that rested before it filled.",
    )
    taker_rate: float = parameter(
        0.0040,
        minimum=0.0,
        maximum=0.1,
        step=0.0001,
        number_format="%.4f",
        description="Charged on an order that crossed to fill at once.",
    )

    def maker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.maker_rate

    def taker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.taker_rate


KRAKEN = FeeSchedule()
