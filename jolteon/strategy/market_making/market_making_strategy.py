from typing import Union

from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.risk_limit.inventory_limit import InventoryLimit
from jolteon.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
    IFairPriceModel,
)
from jolteon.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
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
    """

    def __init__(
        self,
        symbol: str,
        quote_size: float,
        half_spread: float,
        max_inventory: float,
        requote_tolerance: float = 0.0,
        fair_price_model: Union[IFairPriceModel, None] = None,
    ):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        assert quote_size > 0, "quote_size must be positive"
        assert half_spread > 0, "half_spread must be positive"

        self._symbol = symbol
        self._quote_size = quote_size
        self._half_spread = half_spread
        self._requote_tolerance = requote_tolerance
        self._fair_price_model = fair_price_model or MidPriceFairPriceModel()
        self._inventory_limit = InventoryLimit(max_inventory)

        self._live_orders: dict[MarketSide, Order] = {}

        self.order_event = signal("order")
        self.cancel_order_event = signal("cancel_order")

    @property
    def inventory(self) -> float:
        return self._inventory_limit.position

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        fair_price = self._fair_price_model.calculate(
            FairPriceContext(bbo=bbo)
        )
        self._requote(MarketSide.BUY, fair_price - self._half_spread)
        self._requote(MarketSide.SELL, fair_price + self._half_spread)

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        self._inventory_limit.record_fill(trade)

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
                client_order_id=live_order.client_order_id,
            )
