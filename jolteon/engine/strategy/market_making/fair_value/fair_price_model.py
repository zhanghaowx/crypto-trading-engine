from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.engine.core.event.signal import signal
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot


@dataclass
class FairPrice:
    bid: float
    ask: float


@dataclass
class FairPriceUpdate:
    symbol: str
    model: str
    bid_fair_price: float
    ask_fair_price: float


class IFairPriceModel(ABC):
    def __init__(self):
        self.fair_price_event = signal("fair_price")

    def calculate(self, context: BookSnapshot) -> FairPrice:
        """
        Returns: The fair bid/ask price of the market given the current
        context, also published on `fair_price_event` so a history of
        every model's output is recorded regardless of who asked for it.
        Each update names the model that produced it, so a model wrapping
        another one leaves two distinguishable series rather than one
        mixed table.
        """
        fair_price = self._calculate(context)
        self.fair_price_event.send(
            self.fair_price_event,
            fair_price_update=FairPriceUpdate(
                symbol=context.bbo.symbol,
                model=type(self).__name__,
                bid_fair_price=fair_price.bid,
                ask_fair_price=fair_price.ask,
            ),
        )
        return fair_price

    @abstractmethod
    def _calculate(self, context: BookSnapshot) -> FairPrice:
        raise NotImplementedError  # pragma: no cover
