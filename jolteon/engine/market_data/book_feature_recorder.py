from dataclasses import dataclass

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.market_data.core.book_features import imbalance, vwap
from jolteon.engine.market_data.core.order_book import OrderBook, PriceLevel


@dataclass
class BookFeatureSnapshot:
    symbol: str
    bid_price: float
    bid_quantity: float
    ask_price: float
    ask_quantity: float
    imbalance_1: float
    imbalance_5: float
    imbalance_10: float
    depth_weighted_bid: float | None
    depth_weighted_ask: float | None


class BookFeatureRecorder(SignalSubscriber):
    """
    Turns each published order book into a small fixed set of columns.
    A book is too wide to record as it stands - every level becomes a
    column of its own and the writer widens its table as the book moves -
    while the features below stay one narrow row per update, which is what
    a signal evaluation page can plot and what a future replay would need.
    """

    DEPTH = 10

    def __init__(self):
        self.book_features_event = signal("book_features")

    @subscribe("order_book_feed")
    def on_order_book(self, _: str, order_book: OrderBook):
        bbo = order_book.bbo()
        if not bbo:
            return

        bids = order_book.bids(BookFeatureRecorder.DEPTH)
        asks = order_book.asks(BookFeatureRecorder.DEPTH)

        self.book_features_event.send(
            self.book_features_event,
            book_features=BookFeatureSnapshot(
                symbol=bbo.symbol,
                bid_price=bbo.bid_price,
                bid_quantity=bbo.bid_quantity,
                ask_price=bbo.ask_price,
                ask_quantity=bbo.ask_quantity,
                imbalance_1=imbalance(bids[:1], asks[:1]),
                imbalance_5=imbalance(bids[:5], asks[:5]),
                imbalance_10=imbalance(bids, asks),
                depth_weighted_bid=self._depth_weighted(bids),
                depth_weighted_ask=self._depth_weighted(asks),
            ),
        )

    @staticmethod
    def _depth_weighted(levels: list[PriceLevel]) -> float | None:
        """
        Returns: The average price of sweeping every level given, so the
        number needs no size convention to read it by.
        """
        return vwap(levels, sum(level.quantity for level in levels))
