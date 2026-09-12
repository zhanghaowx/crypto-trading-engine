from typing import Union

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.health_monitor.heartbeat import Heartbeater
from jolteon.engine.core.id_generator import id_generator
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.order_book import OrderBook
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.risk_limit.inventory_limit import InventoryLimit
from jolteon.engine.risk_limit.risk_limit import RiskLimitLevel
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)
from jolteon.engine.strategy.market_making.quote_offset import (
    IQuoteOffsetService,
    StaticQuoteOffsetService,
)


class MarketMakingStrategy(Heartbeater, SignalSubscriber):
    """
    A simple two-sided market making strategy:
    - Fair price comes from a pluggable IFairPriceModel (mid-price by
      default).
    - Quotes a fixed size on both sides, as far outside the fair price as
      a pluggable IQuoteOffsetService asks for.
    - Inventory is capped by a hard limit: once the cap is hit on one side,
      that side stops quoting until fills bring the position back within
      bounds.
    - Quote size, the inventory cap and the requote tolerance come from a
      pluggable IParameterService (fixed, conservative defaults if none is
      given), read on every tick so they can be retuned while running.
    """

    def __init__(
        self,
        symbol: str,
        requote_tolerance: float | None = None,
        fair_price_model: Union[IFairPriceModel, None] = None,
        parameter_service: Union[IParameterService, None] = None,
        quote_offset_service: Union[IQuoteOffsetService, None] = None,
    ):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self._symbol = symbol
        self._parameter_service = parameter_service or StaticParameterService()
        self._requote_tolerance = requote_tolerance
        self._quote_offset_service = (
            quote_offset_service or StaticQuoteOffsetService()
        )
        self._fair_price_model = fair_price_model or MidPriceFairPriceModel()
        self._inventory_limit = InventoryLimit(
            parameter_service=self._parameter_service, symbol=symbol
        )

        self._live_orders: dict[MarketSide, Order] = {}
        self._order_book: OrderBook | None = None

        self.order_event = signal("order")
        self.cancel_order_event = signal("cancel_order")
        self.risk_limit_event = signal("risk_limit_snapshot")

    @property
    def inventory(self) -> float:
        return self._inventory_limit.position

    def send_heartbeat(self):
        super().send_heartbeat()
        self._emit_risk_limit_snapshot()

    def _emit_risk_limit_snapshot(self):
        self.risk_limit_event.send(
            self.risk_limit_event,
            risk_limit=RiskLimitLevel(
                name="inventory",
                symbol=self._symbol,
                current=self.inventory,
                maximum=self._inventory_limit.max_inventory,
            ),
        )

    @subscribe("order_book_feed")
    def on_order_book(self, _: str, order_book: OrderBook):
        self._order_book = order_book

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        params = self._parameters()
        context = self._context(bbo, params.book_depth)
        fair_price = self._fair_price_model.calculate(context)
        offset = self._quote_offset_service.calculate(context)
        self._requote(MarketSide.BUY, fair_price.bid - offset.bid, params)
        self._requote(MarketSide.SELL, fair_price.ask + offset.ask, params)

    def _parameters(self) -> MarketMakingParameters:
        return self._parameter_service.get(
            MarketMakingParameters, self._symbol
        )

    def _context(self, bbo: BBO, depth: int) -> BookSnapshot:
        book = self._order_book
        if not book:
            return BookSnapshot(bbo=bbo)

        return BookSnapshot(
            bbo=bbo, bids=tuple(book.bids(depth)), asks=tuple(book.asks(depth))
        )

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        self._inventory_limit.record_fill(trade)
        self._emit_risk_limit_snapshot()

        live_order = self._live_orders.get(trade.side)
        if live_order and live_order.client_order_id == trade.client_order_id:
            # Don't bother tracking the partially filled remainder: cancel
            # it and let the next requote place a fresh, full-size quote.
            self._cancel(trade.side)

    def _requote(
        self,
        side: MarketSide,
        desired_price: float,
        params: MarketMakingParameters,
    ):
        live_order = self._live_orders.get(side)

        if not self._inventory_limit.can_quote(side):
            if live_order:
                self._cancel(side)
            return

        tolerance = self._requote_tolerance
        if tolerance is None:
            tolerance = params.requote_tolerance
        if live_order:
            assert live_order.price is not None
            if abs(live_order.price - desired_price) <= tolerance:
                return

        if live_order:
            self._cancel(side)

        order = Order(
            client_order_id=str(id_generator().next()),
            order_type=OrderType.LIMIT_ORDER,
            symbol=self._symbol,
            price=desired_price,
            quantity=params.quote_size,
            side=side,
            creation_time=time_manager().now(),
        )
        self._live_orders[side] = order
        self.order_event.send(self.order_event, order=order)

    def _cancel(self, side: MarketSide):
        live_order = self._live_orders.pop(side, None)
        if live_order:
            self.cancel_order_event.send(
                self.cancel_order_event,
                cancel_order=CancelOrder(
                    client_order_id=live_order.client_order_id
                ),
            )
