from abc import ABC, abstractmethod
from enum import StrEnum

from jolteon.engine.core.health_monitor.heartbeat import Heartbeater
from jolteon.engine.market_data.core.events import Events


class Channel(StrEnum):
    MARKET_TRADE = "market_trade"
    TICKER = "ticker"
    ORDER_BOOK = "order_book"


class IMarketDataFeed(Heartbeater, ABC):
    """
    One source of market data for one symbol, live or replayed. It decodes
    whatever its venue speaks and publishes the result on `events`, so
    nothing downstream knows which venue produced a price.
    """

    def __init__(self, name: str, interval_in_seconds: float):
        super().__init__(name, interval_in_seconds)
        self.events = Events()

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
