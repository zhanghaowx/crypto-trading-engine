from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.market_data.core.bbo import BBO


@dataclass
class FairPriceContext:
    """
    Market context available to a fair price model when it is asked to
    compute a fair price. New fields (e.g. inventory, volatility, recent
    trades) can be added here as more sophisticated models need them,
    without breaking IFairPriceModel's signature.
    """

    bbo: BBO


class IFairPriceModel(ABC):
    @abstractmethod
    def calculate(self, context: FairPriceContext) -> float:
        """
        Returns: The fair price of the market given the current context.
        """
        raise NotImplementedError  # pragma: no cover
