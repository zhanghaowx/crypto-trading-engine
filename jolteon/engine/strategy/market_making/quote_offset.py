from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.fee_schedule import KRAKEN, FeeSchedule
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot


@dataclass(frozen=True)
class QuoteOffset:
    """
    How far outside the fair price to quote on each side, in quote
    currency per unit of base. The bid sits `bid` below the fair bid and
    the ask sits `ask` above the fair ask, so both widen the quote and
    neither may be negative.
    """

    bid: float
    ask: float


@dataclass
class QuoteOffsetUpdate:
    symbol: str
    service: str
    bid_offset: float
    ask_offset: float


class IQuoteOffsetService(ABC):
    """
    Decides how much edge to demand over the fair price, as opposed to
    where the fair price is - a fair price model moves both sides
    together to say the true price lies elsewhere, while an offset pushes
    each side outward to say what the quote must earn to be worth making.
    Whatever a service needs to decide that it sources itself.
    """

    def __init__(self):
        self.quote_offset_event = signal("quote_offset")

    def calculate(self, context: BookSnapshot) -> QuoteOffset:
        """
        Returns: The offset to quote at either side of the fair price,
        also published on `quote_offset_event` so a history of every
        service's output is recorded regardless of who asked for it.
        """
        offset = self._calculate(context)
        assert offset.bid >= 0.0, "bid offset must not be negative"
        assert offset.ask >= 0.0, "ask offset must not be negative"

        self.quote_offset_event.send(
            self.quote_offset_event,
            quote_offset_update=QuoteOffsetUpdate(
                symbol=context.bbo.symbol,
                service=type(self).__name__,
                bid_offset=offset.bid,
                ask_offset=offset.ask,
            ),
        )
        return offset

    @abstractmethod
    def _calculate(self, context: BookSnapshot) -> QuoteOffset:
        raise NotImplementedError  # pragma: no cover


class StaticQuoteOffsetService(IQuoteOffsetService):
    """
    The same half spread on both sides whatever the market is doing.
    Ignores fees, so at a high enough price it quotes inside the cost of
    trading; it is the conservative starting point a live session can be
    run from, not a service to trade a real book on.
    """

    DEFAULT_HALF_SPREAD = 50.0

    def __init__(self, half_spread: float = DEFAULT_HALF_SPREAD):
        super().__init__()
        assert half_spread > 0, "half_spread must be positive"
        self._half_spread = half_spread

    def _calculate(self, context: BookSnapshot) -> QuoteOffset:
        return QuoteOffset(bid=self._half_spread, ask=self._half_spread)


class FeeAwareQuoteOffsetService(IQuoteOffsetService):
    """
    Charges a fixed edge on top of the fee the venue will take, so a fill
    at the quoted price earns `edge` per unit rather than `edge` less
    whatever the fee turned out to be.

    The fee is a fraction of notional, so its contribution grows with the
    price and the quote widens as the market rallies. Quoting a resting
    limit order makes the maker rate the one that applies.
    """

    def __init__(self, edge: float, fees: FeeSchedule = KRAKEN):
        super().__init__()
        assert edge > 0, "edge must be positive"
        self._edge = edge
        self._fees = fees

    def _calculate(self, context: BookSnapshot) -> QuoteOffset:
        return QuoteOffset(
            bid=self._edge + self._fees.maker_fee(context.bbo.bid_price, 1.0),
            ask=self._edge + self._fees.maker_fee(context.bbo.ask_price, 1.0),
        )
