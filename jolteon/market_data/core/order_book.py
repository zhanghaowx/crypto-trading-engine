from dataclasses import dataclass

from jolteon.core.side import MarketSide


@dataclass
class SidedOrderBook:
    """
    Represent the order book for a sided market
    """

    side: MarketSide
    levels: dict[float, float]
    total_volume: float


class OrderBook:
    """
    Represent the order book for one symbol
    """

    def __init__(self):
        self.bids = SidedOrderBook(
            side=MarketSide.BUY, levels={}, total_volume=0
        )
        self.asks = SidedOrderBook(
            side=MarketSide.SELL, levels={}, total_volume=0
        )

    def add_bid(self, price, quantity):
        """
        Add a bid to the order book
        Args:
            price: Price of the bid
            quantity: Quantity of the bid

        Returns:
            None
        """
        self.bids.levels[price] = self.bids.levels.get(price, 0) + quantity
        self.bids.total_volume += quantity

    def add_ask(self, price, quantity):
        """
        Add an ask to the order book

        Args:
            price: Price of the ask
            quantity: Quantity of the ask

        Returns:
            None
        """
        self.asks.levels[price] = self.asks.levels.get(price, 0) + quantity
        self.asks.total_volume += quantity
