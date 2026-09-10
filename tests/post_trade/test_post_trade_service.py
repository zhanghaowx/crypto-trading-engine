import unittest
import uuid
from datetime import datetime

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.trade import Trade
from jolteon.position.position_manager import PositionUpdate
from jolteon.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.post_trade.post_trade_service import PostTradeService


class TestPostTradeService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.post_trade_service = PostTradeService()

        self.records = list[DecoratedOrderFill]()
        self.post_trade_service.decorated_order_fill_event.connect(
            self._on_decorated_order_fill
        )

    def _on_decorated_order_fill(
        self, _, decorated_order_fill: DecoratedOrderFill
    ):
        self.records.append(decorated_order_fill)

    @staticmethod
    def create_bbo(
        bid_price: float, ask_price: float, symbol: str = "BTC/USD"
    ):
        return BBO(
            symbol=symbol,
            bid_price=bid_price,
            bid_quantity=1.0,
            ask_price=ask_price,
            ask_quantity=1.0,
        )

    @staticmethod
    def create_fill(
        trade_id: int,
        side: MarketSide,
        price: float,
        quantity: float,
        symbol: str = "BTC/USD",
        fee: float = 0.1,
    ):
        return Trade(
            trade_id=trade_id,
            client_order_id=str(trade_id),
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=price,
            fee=fee,
            quantity=quantity,
            transaction_time=datetime.now(pytz.utc),
        )

    def notify_position(self, volume: float, symbol: str = "BTC/USD"):
        """Simulates PositionManager's position_updated arriving for this
        fill, ahead of the fill itself - the ordering PostTradeService
        relies on in production (see PostTradeService.on_fill)."""
        self.post_trade_service.on_position_updated(
            "_", PositionUpdate(symbol=symbol, volume=volume)
        )

    async def test_skips_fill_with_no_bbo_seen_yet(self):
        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )

        self.assertEqual([], self.records)

    async def test_decorates_first_fill_with_zero_inventory_before(self):
        self.post_trade_service.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.notify_position(1.0)

        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )

        self.assertEqual(1, len(self.records))
        record = self.records[0]
        self.assertEqual(1, record.trade_id)
        self.assertEqual(MarketSide.BUY, record.side)
        self.assertEqual(100.0, record.fill_price)
        self.assertEqual(1.0, record.fill_qty)
        self.assertEqual(100.0, record.fair_price_at_fill)
        self.assertEqual(0.0, record.inventory_before)
        self.assertEqual(1.0, record.inventory_after)
        self.assertIsNone(record.fair_price_100ms)
        self.assertIsNone(record.fair_price_1s)
        self.assertIsNone(record.fair_price_5s)
        self.assertIsNone(record.fair_price_30s)

    async def test_decorates_subsequent_fill_with_prior_inventory(self):
        self.post_trade_service.on_bbo("_", self.create_bbo(99.0, 101.0))

        self.notify_position(1.0)
        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )
        self.notify_position(1.5)
        self.post_trade_service.on_fill(
            "_", self.create_fill(2, MarketSide.BUY, 100.0, 0.5)
        )

        self.assertEqual(2, len(self.records))
        self.assertEqual(1.0, self.records[1].inventory_before)
        self.assertEqual(1.5, self.records[1].inventory_after)

    async def test_horizon_callback_fills_field_without_clobbering_others(
        self,
    ):
        self.post_trade_service.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.notify_position(1.0)
        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )

        self.post_trade_service.on_bbo("_", self.create_bbo(100.0, 102.0))
        self.post_trade_service._on_horizon(1, "fair_price_100ms")

        self.assertEqual(2, len(self.records))
        latest = self.records[-1]
        self.assertEqual(101.0, latest.fair_price_100ms)
        self.assertEqual(100.0, latest.fair_price_at_fill)
        self.assertIsNone(latest.fair_price_1s)
        self.assertIsNone(latest.fair_price_5s)
        self.assertIsNone(latest.fair_price_30s)

    async def test_final_horizon_callback_drops_the_pending_fill(self):
        self.post_trade_service.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.notify_position(1.0)
        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )

        self.assertEqual(1, len(self.post_trade_service._pending_fills))
        self.post_trade_service._on_horizon(1, "fair_price_30s")
        self.assertEqual(0, len(self.post_trade_service._pending_fills))

    async def test_horizon_callback_for_an_unknown_fill_is_a_no_op(self):
        self.post_trade_service._on_horizon(999, "fair_price_100ms")

        self.assertEqual([], self.records)
