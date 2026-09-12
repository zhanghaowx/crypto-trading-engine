from abc import ABC, abstractmethod

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
)


class FeeSchedule(ParameterGroup, ABC):
    """
    What a venue charges to trade, as a fraction of the notional filled.
    The maker rate applies to an order that rested on the book before it
    filled, the taker rate to one that crossed to fill immediately.

    Every venue prices those two rates off something different - traded
    volume, assets held, which pair, a negotiated tier - so a venue
    declares its own schedule as a subclass and states whatever it is
    charged on in its own terms. What is shared is only the arithmetic
    below: a fee is a rate against notional.
    """

    @property
    @abstractmethod
    def maker_rate(self) -> float:
        raise NotImplementedError  # pragma: no cover

    @property
    @abstractmethod
    def taker_rate(self) -> float:
        raise NotImplementedError  # pragma: no cover

    def maker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.maker_rate

    def taker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.taker_rate
