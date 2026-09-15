from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import Order
from jolteon.engine.market_data.core.order_book import OrderBook


@dataclass
class QueuePosition:
    """Displayed quantity assumed to be ahead of one simulated order."""

    ahead_quantity: float

    def consume(self, quantity: float) -> float:
        """Consume queue ahead and return volume available to our order."""
        consumed = min(self.ahead_quantity, quantity)
        self.ahead_quantity -= consumed
        return quantity - consumed


class QueuePositionModel(ABC):
    """Calculates initial simulated queue position from available data."""

    @abstractmethod
    def create(
        self, order: Order, order_book: OrderBook | None, bbo: BBO | None
    ) -> QueuePosition:
        raise NotImplementedError  # pragma: no cover


class L2QueuePositionModel(QueuePositionModel):
    def create(
        self, order: Order, order_book: OrderBook | None, bbo: BBO | None
    ) -> QueuePosition:
        assert order.price is not None, "Limit orders must have a price"
        if order_book is not None:
            ahead = order_book.quantity_at(
                order.price, bid=order.side == MarketSide.BUY
            )
        elif bbo is not None and (
            (order.side == MarketSide.BUY and order.price == bbo.bid_price)
            or (order.side == MarketSide.SELL and order.price == bbo.ask_price)
        ):
            ahead = (
                bbo.bid_quantity
                if order.side == MarketSide.BUY
                else bbo.ask_quantity
            )
        else:
            ahead = 0.0
        return QueuePosition(ahead)
