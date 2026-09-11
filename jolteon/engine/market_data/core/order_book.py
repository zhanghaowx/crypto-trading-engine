import bisect
from dataclasses import dataclass
from datetime import datetime

from jolteon.engine.market_data.core.bbo import BBO


@dataclass(frozen=True)
class PriceLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class BookUpdate:
    """
    One exchange-neutral change to an order book. A quantity of zero means
    the level is gone. Translating a wire format into this is the entire
    job of an exchange adapter.
    """

    symbol: str
    bids: list[PriceLevel]
    asks: list[PriceLevel]
    is_snapshot: bool
    exchange_time: datetime


class OrderBook:
    """
    A level 2 order book for one symbol: the resting quantity at each
    price on each side, kept in price order.

    Both sides are stored ascending by price and maintained with a binary
    search, so the best bid is the last bid and the best ask is the first
    ask. Reads hand back the best levels first, whichever side they come
    from.

    A venue publishing only the top `depth` levels does not always say
    when a level falls out of that window, so a book given a depth trims
    itself back to it after every update. Without that, a level that left
    the window lingers and reappears as the market moves back over it.
    """

    # SignalRecorder would flatten a book into one column per level per
    # side, widening its table as the book moves. Derived features are
    # recorded instead.
    RECORDED = False

    def __init__(self, symbol: str, depth: int | None = None):
        assert depth is None or depth > 0, "depth must be positive"
        self.symbol = symbol
        self.exchange_time: datetime | None = None
        self._depth = depth
        self._bids: list[PriceLevel] = []
        self._asks: list[PriceLevel] = []

    def apply(self, update: BookUpdate) -> None:
        if update.is_snapshot:
            self.clear()

        for level in update.bids:
            self._apply_level(self._bids, level)
        for level in update.asks:
            self._apply_level(self._asks, level)

        if self._depth is not None:
            del self._bids[: -self._depth]
            del self._asks[self._depth :]

        self.exchange_time = update.exchange_time

    def clear(self) -> None:
        self._bids.clear()
        self._asks.clear()

    def best_bid(self) -> PriceLevel | None:
        return self._bids[-1] if self._bids else None

    def best_ask(self) -> PriceLevel | None:
        return self._asks[0] if self._asks else None

    def bbo(self) -> BBO | None:
        best_bid, best_ask = self.best_bid(), self.best_ask()
        if not best_bid or not best_ask:
            return None

        return BBO(
            symbol=self.symbol,
            bid_price=best_bid.price,
            bid_quantity=best_bid.quantity,
            ask_price=best_ask.price,
            ask_quantity=best_ask.quantity,
        )

    def bids(self, depth: int) -> list[PriceLevel]:
        """Returns: Up to `depth` bids, highest price first."""
        if depth <= 0:
            return []
        return self._bids[: -depth - 1 : -1]

    def asks(self, depth: int) -> list[PriceLevel]:
        """Returns: Up to `depth` asks, lowest price first."""
        if depth <= 0:
            return []
        return self._asks[:depth]

    @staticmethod
    def _apply_level(levels: list[PriceLevel], level: PriceLevel) -> None:
        index = bisect.bisect_left(levels, level.price, key=lambda x: x.price)

        if index < len(levels) and levels[index].price == level.price:
            if level.quantity > 0:
                levels[index] = level
            else:
                del levels[index]
        elif level.quantity > 0:
            levels.insert(index, level)
