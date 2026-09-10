from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.core.event.signal import signal
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


@dataclass
class FairPrice:
    bid: float
    ask: float


@dataclass
class FairPriceUpdate:
    symbol: str
    bid_fair_price: float
    ask_fair_price: float


class IFairPriceModel(ABC):
    def __init__(self):
        self.fair_price_event = signal("fair_price")

    def calculate(self, context: FairPriceContext) -> FairPrice:
        """
        Returns: The fair bid/ask price of the market given the current
        context, also published on `fair_price_event` so a history of
        every model's output is recorded regardless of who asked for it.
        """
        fair_price = self._calculate(context)
        self.fair_price_event.send(
            self.fair_price_event,
            fair_price_update=FairPriceUpdate(
                symbol=context.bbo.symbol,
                bid_fair_price=fair_price.bid,
                ask_fair_price=fair_price.ask,
            ),
        )
        return fair_price

    @abstractmethod
    def _calculate(self, context: FairPriceContext) -> FairPrice:
        raise NotImplementedError  # pragma: no cover
