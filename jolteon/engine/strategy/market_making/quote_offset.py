from abc import ABC, abstractmethod
from dataclasses import dataclass

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.parameters import (
    QuoteOffsetParameters,
)


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

    def __init__(
        self,
        half_spread: float | None = None,
        parameter_service: IParameterService | None = None,
    ):
        super().__init__()
        assert half_spread is None or half_spread > 0, (
            "half_spread must be positive"
        )
        self._half_spread = half_spread
        self._parameter_service = parameter_service or StaticParameterService()

    def _calculate(self, context: BookSnapshot) -> QuoteOffset:
        half_spread = self._half_spread
        if half_spread is None:
            half_spread = self._parameter_service.get(
                QuoteOffsetParameters, context.bbo.symbol
            ).half_spread
        return QuoteOffset(bid=half_spread, ask=half_spread)


class FeeAwareQuoteOffsetService(IQuoteOffsetService):
    """
    Charges a fixed edge on top of the fee the venue will take, so a fill
    at the quoted price earns `edge` per unit rather than `edge` less
    whatever the fee turned out to be.

    The fee is a fraction of notional, so its contribution grows with the
    price and the quote widens as the market rallies. Quoting a resting
    limit order makes the maker rate the one that applies.
    """

    def __init__(
        self,
        fee_schedule: type[FeeSchedule],
        edge: float | None = None,
        parameter_service: IParameterService | None = None,
    ):
        super().__init__()
        assert edge is None or edge > 0, "edge must be positive"
        self._fee_schedule = fee_schedule
        self._edge = edge
        self._parameter_service = parameter_service or StaticParameterService()

    def _calculate(self, context: BookSnapshot) -> QuoteOffset:
        symbol = context.bbo.symbol
        edge = self._edge
        if edge is None:
            edge = self._parameter_service.get(
                QuoteOffsetParameters, symbol
            ).edge
        fees = self._parameter_service.get(self._fee_schedule, symbol)
        return QuoteOffset(
            bid=edge + fees.maker_fee(context.bbo.bid_price, 1.0),
            ask=edge + fees.maker_fee(context.bbo.ask_price, 1.0),
        )
