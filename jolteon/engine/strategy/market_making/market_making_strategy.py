from typing import Union

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.health_monitor.heartbeat import Heartbeater
from jolteon.engine.core.id_generator import id_generator
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.order_book import OrderBook
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.risk_limit.inventory_limit import InventoryLimit
from jolteon.engine.risk_limit.risk_limit import RiskLimitLevel
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.parameters import (
    IParameterService,
    StaticParameterService,
)


class MarketMakingStrategy(Heartbeater, SignalSubscriber):
    """
    A simple two-sided market making strategy:
    - Fair price comes from a pluggable IFairPriceModel (mid-price by
      default).
    - Quotes a fixed size at a fixed half-spread around the fair price on
      both sides.
    - Inventory is capped by a hard limit: once the cap is hit on one side,
      that side stops quoting until fills bring the position back within
      bounds. No inventory-based price skewing yet.
    - Quote size, half-spread and the inventory cap come from a pluggable
      IParameterService (fixed, conservative defaults if none is given),
      so callers such as the CLI don't need to know or pass tuning values.
    """

    def __init__(
        self,
        symbol: str,
        requote_tolerance: float = 0.0,
        fair_price_model: Union[IFairPriceModel, None] = None,
        parameter_service: Union[IParameterService, None] = None,
    ):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        params = (parameter_service or StaticParameterService()).get(symbol)
        assert params.quote_size > 0, "quote_size must be positive"
        assert params.half_spread > 0, "half_spread must be positive"

        self._symbol = symbol
        self._quote_size = params.quote_size
        self._half_spread = params.half_spread
        self._requote_tolerance = requote_tolerance
        self._fair_price_model = fair_price_model or MidPriceFairPriceModel()
        self._inventory_limit = InventoryLimit(params.max_inventory)

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
        fair_price = self._fair_price_model.calculate(
            FairPriceContext(bbo=bbo, order_book=self._order_book)
        )
        self._requote(MarketSide.BUY, fair_price.bid - self._half_spread)
        self._requote(MarketSide.SELL, fair_price.ask + self._half_spread)

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        self._inventory_limit.record_fill(trade)
        self._emit_risk_limit_snapshot()

        live_order = self._live_orders.get(trade.side)
        if live_order and live_order.client_order_id == trade.client_order_id:
            # Don't bother tracking the partially filled remainder: cancel
            # it and let the next requote place a fresh, full-size quote.
            self._cancel(trade.side)

    def _requote(self, side: MarketSide, desired_price: float):
        live_order = self._live_orders.get(side)

        if not self._inventory_limit.can_quote(side):
            if live_order:
                self._cancel(side)
            return

        if live_order:
            assert live_order.price is not None
            if (
                abs(live_order.price - desired_price)
                <= self._requote_tolerance
            ):
                return

        if live_order:
            self._cancel(side)

        order = Order(
            client_order_id=str(id_generator().next()),
            order_type=OrderType.LIMIT_ORDER,
            symbol=self._symbol,
            price=desired_price,
            quantity=self._quote_size,
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
