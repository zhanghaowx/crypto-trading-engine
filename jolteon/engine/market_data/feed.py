import logging
from abc import ABC, abstractmethod
from enum import StrEnum, auto

from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.health_monitor.heartbeat import (
    Heartbeater,
)
from jolteon.engine.market_data.core.events import Events
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    RecordedBookUpdate,
)


class Channel(StrEnum):
    MARKET_TRADE = "market_trade"
    TICKER = "ticker"
    ORDER_BOOK = "order_book"
    INSTRUMENT = "instrument"


class IMarketDataFeed(Heartbeater, ABC):
    """
    One source of market data for one symbol, live or replayed. It decodes
    whatever its venue speaks and publishes the result on `events`, so
    nothing downstream knows which venue produced a price.
    """

    class ErrorCode(StrEnum):
        ORDER_BOOK_OUT_OF_SYNC = auto()

    def __init__(
        self,
        name: str,
        interval_in_seconds: float | None = None,
        health_monitor: HealthMonitor | None = None,
    ):
        super().__init__(name, interval_in_seconds, health_monitor)
        self.events = Events()
        self._book_record_sequence = 0

    @property
    @abstractmethod
    def channels(self) -> frozenset[Channel]:
        """
        Returns: What this feed publishes, so a consumer that needs depth
        can find out at wiring time instead of discovering an absent book
        on the first tick.
        """
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    async def connect(self, symbol: str, *args) -> None:
        """
        Run the feed until it is done or cancelled. Implementations
        decorate this with @starts_heartbeating so the heartbeat runs on
        the loop doing the feed's real work.
        """
        raise NotImplementedError  # pragma: no cover

    async def resync_order_book(self, order_book: OrderBook) -> None:
        """
        Rebuild a book that no longer matches the venue's. How a desync is
        detected differs per venue; recovering from one does not, so the
        sequence lives here: drop what we have, ask for a fresh snapshot,
        and report degraded until one arrives.
        """
        logging.warning(
            f"Order book for {order_book.symbol} is out of sync, "
            f"requesting a fresh snapshot"
        )
        order_book.clear()
        self.add_issue(
            HealthState.CRITICAL,
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
        )
        await self._request_order_book_snapshot(order_book.symbol)

    def on_order_book_synced(self) -> None:
        self.remove_issue(
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name
        )

    def publish_order_book(
        self, order_book: OrderBook, update: BookUpdate
    ) -> None:
        """Publish both the compact replay record and current L2 view."""
        self._dispatch_isolating_receiver_errors(
            self.events.order_book_update,
            book_update=self.record_order_book_update(update),
        )
        self._dispatch_isolating_receiver_errors(
            self.events.order_book, order_book=order_book
        )

    @staticmethod
    def _dispatch_isolating_receiver_errors(signal, **kwargs) -> None:
        try:
            signal.send(signal, **kwargs)
        except Exception as error:
            logging.error(
                "A receiver of signal '%s' raised an exception: %s",
                signal.name,
                error,
                exc_info=True,
            )

    def record_order_book_update(
        self, update: BookUpdate
    ) -> RecordedBookUpdate:
        self._book_record_sequence += 1
        return RecordedBookUpdate.from_update(
            update, sequence=self._book_record_sequence
        )

    async def _request_order_book_snapshot(self, symbol: str) -> None:
        """Ask the venue to send the book again from scratch. Only feeds
        publishing Channel.ORDER_BOOK ever reach this."""
        raise NotImplementedError  # pragma: no cover
