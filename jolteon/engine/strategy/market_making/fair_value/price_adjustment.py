from abc import ABC, abstractmethod

from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)


class IFairPriceAdjustment(SignalSubscriber, ABC):
    """
    One self-contained input into a composite fair price model: it sources
    whatever data it needs on its own (by subscribing to signals, or from
    `FairPriceContext` alone), holds its own tuning, and returns a single
    price offset ready to add to the base fair price. Nothing outside an
    adjustment needs to know how it arrived at that number.

    Returning 0.0 is how an adjustment abstains - while it is still
    warming up, or when it simply has nothing to say right now.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Column name this adjustment is recorded under."""
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def adjustment(self, context: FairPriceContext) -> float:
        raise NotImplementedError  # pragma: no cover
