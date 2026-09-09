import unittest
import uuid
from datetime import datetime

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.strategy.market_making.parameters import StaticParameterService


class TestMarketMakingStrategy(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orders = list[Order]()
        self.cancelled_ids = list[str]()

        self.strategy = MarketMakingStrategy(
            symbol="BTC/USD",
            requote_tolerance=0.0,
            parameter_service=StaticParameterService(
                quote_size=0.01,
                half_spread=1.0,
                max_inventory=0.02,
            ),
        )
        self.strategy.order_event.connect(self._on_order)
        self.strategy.cancel_order_event.connect(self._on_cancel_order)

    def _on_order(self, _, order: Order):
        self.orders.append(order)

    def _on_cancel_order(self, _, client_order_id: str):
        self.cancelled_ids.append(client_order_id)

    @staticmethod
    def create_bbo(bid_price: float, ask_price: float):
        return BBO(
            symbol="BTC/USD",
            bid_price=bid_price,
            bid_quantity=1.0,
            ask_price=ask_price,
            ask_quantity=1.0,
        )

    @staticmethod
    def create_fill(client_order_id: str, side: MarketSide, price: float):
        return Trade(
            trade_id=1,
            client_order_id=client_order_id,
            symbol="BTC/USD",
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=price,
            fee=0.0,
            quantity=0.01,
            transaction_time=datetime.now(pytz.utc),
        )

    async def test_quotes_both_sides_around_fair_price(self):
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))

        self.assertEqual(2, len(self.orders))
        buy_order = next(o for o in self.orders if o.side == MarketSide.BUY)
        sell_order = next(o for o in self.orders if o.side == MarketSide.SELL)
        self.assertEqual(99.0, buy_order.price)
        self.assertEqual(101.0, sell_order.price)
        self.assertEqual(OrderType.LIMIT_ORDER, buy_order.order_type)

    async def test_does_not_requote_within_tolerance(self):
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.assertEqual(2, len(self.orders))

        # Same fair price -> no new orders, no cancels
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.assertEqual(2, len(self.orders))
        self.assertEqual(0, len(self.cancelled_ids))

    async def test_requotes_when_price_moves(self):
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        buy_order = next(o for o in self.orders if o.side == MarketSide.BUY)

        self.strategy.on_bbo("_", self.create_bbo(100.0, 102.0))

        self.assertIn(buy_order.client_order_id, self.cancelled_ids)
        self.assertEqual(4, len(self.orders))
        latest_buy = self.orders[-2]
        self.assertEqual(100.0, latest_buy.price)

    async def test_stops_quoting_buy_side_once_inventory_cap_hit(self):
        # Two fills (independent of whatever is currently resting) bring
        # inventory to the 0.02 cap.
        self.strategy.on_fill(
            "_", self.create_fill("unrelated-1", MarketSide.BUY, 99.0)
        )
        self.strategy.on_fill(
            "_", self.create_fill("unrelated-2", MarketSide.BUY, 99.0)
        )
        self.assertEqual(0.02, self.strategy.inventory)

        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))

        # Only the sell side should be quoted now.
        self.assertEqual(1, len(self.orders))
        self.assertEqual(MarketSide.SELL, self.orders[0].side)
