import unittest
import uuid
from datetime import datetime

import pytz

from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.parameters import (
    StaticParameterService,
)


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

    def _on_cancel_order(self, _, cancel_order: CancelOrder):
        self.cancelled_ids.append(cancel_order.client_order_id)

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

    async def test_cancels_own_order_after_it_fills(self):
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        buy_order = next(o for o in self.orders if o.side == MarketSide.BUY)

        self.strategy.on_fill(
            "_",
            self.create_fill(buy_order.client_order_id, MarketSide.BUY, 99.0),
        )

        self.assertEqual([buy_order.client_order_id], self.cancelled_ids)

    async def test_cancels_resting_quote_once_inventory_cap_hit(self):
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        buy_order = next(o for o in self.orders if o.side == MarketSide.BUY)

        for i in range(2):
            self.strategy.on_fill(
                "_", self.create_fill(f"unrelated-{i}", MarketSide.BUY, 99.0)
            )
        self.assertEqual([], self.cancelled_ids)

        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))

        self.assertEqual([buy_order.client_order_id], self.cancelled_ids)

    async def test_hands_the_latest_book_to_the_fair_price_model(self):
        seen = []
        self.strategy._fair_price_model = _RecordingFairPriceModel(seen)
        order_book = self.create_order_book(bid=99.0, ask=101.0)

        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        self.strategy.on_order_book("_", order_book)
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))

        self.assertEqual([(), (PriceLevel(99.0, 1.0),)], seen)

    async def test_carried_levels_do_not_follow_a_later_book_update(self):
        seen = []
        self.strategy._fair_price_model = _RecordingFairPriceModel(seen)
        order_book = self.create_order_book(bid=99.0, ask=101.0)

        self.strategy.on_order_book("_", order_book)
        self.strategy.on_bbo("_", self.create_bbo(99.0, 101.0))
        order_book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(99.0, 0.0), PriceLevel(98.0, 7.0)],
                asks=[],
                is_snapshot=False,
                exchange_time=datetime(2024, 1, 1),
            )
        )

        self.assertEqual([(PriceLevel(99.0, 1.0),)], seen)

    @staticmethod
    def create_order_book(bid: float, ask: float) -> OrderBook:
        order_book = OrderBook("BTC/USD")
        order_book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(bid, 1.0)],
                asks=[PriceLevel(ask, 1.0)],
                is_snapshot=True,
                exchange_time=datetime(2024, 1, 1),
            )
        )
        return order_book


class _RecordingFairPriceModel(IFairPriceModel):
    def __init__(self, seen: list):
        super().__init__()
        self._seen = seen

    def _calculate(self, context: BookSnapshot) -> FairPrice:
        self._seen.append(context.bids)
        return FairPrice(bid=context.bbo.bid_price, ask=context.bbo.ask_price)
