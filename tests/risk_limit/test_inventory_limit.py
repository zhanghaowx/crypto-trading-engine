import unittest
import uuid
from datetime import datetime

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.trade import Trade
from jolteon.risk_limit.inventory_limit import InventoryLimit


class TestInventoryLimit(unittest.TestCase):
    @staticmethod
    def create_trade(side: MarketSide, quantity: float):
        return Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC/USD",
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=100.0,
            fee=0.0,
            quantity=quantity,
            transaction_time=datetime.now(pytz.utc),
        )

    def test_can_quote_both_sides_when_flat(self):
        limit = InventoryLimit(max_inventory=1.0)

        self.assertTrue(limit.can_quote(MarketSide.BUY))
        self.assertTrue(limit.can_quote(MarketSide.SELL))

    def test_blocks_buy_when_long_limit_reached(self):
        limit = InventoryLimit(max_inventory=1.0)

        limit.record_fill(self.create_trade(MarketSide.BUY, 1.0))

        self.assertEqual(1.0, limit.position)
        self.assertFalse(limit.can_quote(MarketSide.BUY))
        self.assertTrue(limit.can_quote(MarketSide.SELL))

    def test_blocks_sell_when_short_limit_reached(self):
        limit = InventoryLimit(max_inventory=1.0)

        limit.record_fill(self.create_trade(MarketSide.SELL, 1.0))

        self.assertEqual(-1.0, limit.position)
        self.assertTrue(limit.can_quote(MarketSide.BUY))
        self.assertFalse(limit.can_quote(MarketSide.SELL))

    def test_position_recovers_after_offsetting_fill(self):
        limit = InventoryLimit(max_inventory=1.0)

        limit.record_fill(self.create_trade(MarketSide.BUY, 1.0))
        self.assertFalse(limit.can_quote(MarketSide.BUY))

        limit.record_fill(self.create_trade(MarketSide.SELL, 0.5))
        self.assertEqual(0.5, limit.position)
        self.assertTrue(limit.can_quote(MarketSide.BUY))
