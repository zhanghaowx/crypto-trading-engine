from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.engine.core.event.signal import signal
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order_book import OrderBook


@dataclass
class FairPriceContext:
    """
    Market context available to a fair price model when it is asked to
    compute a fair price. New fields (e.g. inventory, volatility, recent
    trades) can be added here as more sophisticated models need them,
    without breaking IFairPriceModel's signature.

    `order_book` is None on a feed that publishes no depth, and during
    replay. A model or adjustment that needs depth abstains when it is
    absent rather than guessing.
    """

    bbo: BBO
    order_book: OrderBook | None = None


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

    def calculate(self, context: FairPriceContext) -> FairPrice:
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
    def _calculate(self, context: FairPriceContext) -> FairPrice:
        raise NotImplementedError  # pragma: no cover
