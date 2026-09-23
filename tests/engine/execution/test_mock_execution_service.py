import uuid
from dataclasses import replace
from datetime import datetime
from unittest import IsolatedAsyncioTestCase

import pytz

from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.kraken.fee_schedule import (
    KrakenFeeSchedule,
)
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.execution.unique_trade_id import unique_trade_id
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.data_source import IDataSource


class TestMockExecutionService(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fills = list[Trade]()
        self.health_monitor = HealthMonitor()
        self.execution_service = MockExecutionService(
            KrakenFeeSchedule, health_monitor=self.health_monitor
        )
        self.execution_service.configure(
            StaticParameterService().values(), "BTC/USD"
        )
        self.execution_service.order_fill_event.connect(self.on_fill)
        self.mock_order = Order(
            client_order_id="123",
            order_type=OrderType.MARKET_ORDER,
            symbol="BTC/USD",
            side=MarketSide.BUY,
            price=100,
            quantity=0.0001,
            creation_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.utc),
        )

    async def asyncTearDown(self):
        pass

    def on_fill(self, _: str, trade: Trade):
        self.fills.append(trade)

    async def test_market_order_without_recorded_trade_uses_zero_price(self):
        self.execution_service.on_order(self, self.mock_order)

        self.assertEqual(len(self.fills), 1)
        self.assertEqual(0.0, self.fills[0].price)
        self.assertEqual(0.0, self.fills[0].fee)

    async def test_simulated_fills_have_distinct_mock_unique_trade_ids(self):
        self.execution_service.on_order(self, self.mock_order)
        self.execution_service.on_order(self, self.mock_order)

        first, second = self.fills
        self.assertNotEqual(first.unique_trade_id, second.unique_trade_id)
        for fill in self.fills:
            self.assertEqual("Mock", fill.exchange)
            self.assertEqual("123", fill.exchange_order_id)
            self.assertEqual(
                unique_trade_id("Mock", "123", fill.exchange_execution_id),
                fill.unique_trade_id,
            )

    async def test_final_execution_gate_refuses_order_until_ready(self):
        self.execution_service.health.mark_critical()

        self.execution_service.on_order(self, self.mock_order)
        self.assertEqual([], self.fills)
        self.execution_service.health.mark_healthy()
        self.execution_service.on_order(self, self.mock_order)
        self.assertEqual(1, len(self.fills))

    async def test_an_unconfigured_service_ignores_orders(self):
        self.execution_service._startup_parameters = None

        self.execution_service.on_order(self, self.mock_order)

        self.assertEqual([], self.fills)

    async def test_simulation_settings_require_configuration(self):
        self.execution_service._startup_parameters = None

        with self.assertRaisesRegex(
            RuntimeError, "Execution configuration has not been delivered"
        ):
            self.execution_service.describe_simulation("BTC/USD")

    @staticmethod
    def create_market_trade(side: MarketSide, price: float, quantity: float):
        return Trade(
            exchange_trade_id=1,
            client_order_id="",
            symbol="BTC/USD",
            maker_order_id="",
            taker_order_id="",
            side=side,
            price=price,
            fee=0.0,
            quantity=quantity,
            transaction_time=datetime(2024, 1, 1, tzinfo=pytz.utc),
        )

    def create_limit_order(self, side: MarketSide, price: float):
        return Order(
            client_order_id=str(uuid.uuid4()),
            order_type=OrderType.LIMIT_ORDER,
            symbol="BTC/USD",
            side=side,
            price=price,
            quantity=0.01,
            creation_time=datetime(2024, 1, 1, tzinfo=pytz.utc),
        )

    def rest_book(self, bids=(), asks=()):
        book = OrderBook("BTC/USD")
        book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(price, qty) for price, qty in bids],
                asks=[PriceLevel(price, qty) for price, qty in asks],
                is_snapshot=True,
                exchange_time=self.mock_order.creation_time,
            )
        )
        self.execution_service.on_order_book(self, book)

    async def test_limit_order_rests_until_trade_crosses_it(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        # A trade above our bid shouldn't fill us.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 101.0, 1.0)
        )
        self.assertEqual(0, len(self.fills))

        # A sell print at our level fills us.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 100.0, 0.01)
        )
        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.01, self.fills[0].quantity)
        self.assertEqual(100.0, self.fills[0].price)

    async def test_a_resting_limit_order_is_charged_the_maker_rate(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 100.0, 0.01)
        )

        self.assertEqual(1, len(self.fills))
        self.assertAlmostEqual(
            KrakenFeeSchedule().maker_fee(100.0, 0.01), self.fills[0].fee
        )

    async def test_limit_order_queue_position_delays_fill(self):
        # Someone is displaying 0.02 ahead of us at the bid when we join.
        self.execution_service.on_bbo(
            self,
            BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=0.02,
                ask_price=101.0,
                ask_quantity=1.0,
            ),
        )
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        # This only consumes the size ahead of us, not our own order.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 100.0, 0.02)
        )
        self.assertEqual(0, len(self.fills))

        # Now the queue ahead of us is gone, so this print fills us.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 100.0, 0.01)
        )
        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.01, self.fills[0].quantity)

    async def test_l2_depth_initializes_queue_away_from_the_touch(self):
        book = OrderBook("BTC/USD")
        book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(100.0, 1.0), PriceLevel(99.0, 0.02)],
                asks=[PriceLevel(101.0, 1.0)],
                is_snapshot=True,
                exchange_time=self.mock_order.creation_time,
            )
        )
        self.execution_service.on_order_book(self, book)
        order = self.create_limit_order(MarketSide.BUY, 99.0)
        self.execution_service.on_order(self, order)
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 99.0, 0.02)
        )

        self.assertEqual([], self.fills)

    async def test_limit_order_partial_fills_across_multiple_trades(self):
        order = self.create_limit_order(MarketSide.SELL, 100.0)
        order.quantity = 0.03
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 100.0, 0.01)
        )
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 100.0, 0.01)
        )

        self.assertEqual(2, len(self.fills))
        self.assertAlmostEqual(0.02, sum(f.quantity for f in self.fills))

        # Fully consume the remainder.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 100.0, 0.01)
        )
        self.assertEqual(3, len(self.fills))
        self.assertAlmostEqual(0.03, sum(f.quantity for f in self.fills))

    async def test_limit_order_fills_fully_when_price_trades_through(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        # Price prints below our bid, meaning the book must have cleared
        # through our level already.
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 99.0, 0.5)
        )

        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.01, self.fills[0].quantity)
        self.assertEqual(100.0, self.fills[0].price)

    async def test_trade_through_cannot_fill_more_than_its_quantity(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 99.0, 0.004)
        )

        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.004, self.fills[0].quantity)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 98.0, 0.006)
        )

        self.assertEqual(2, len(self.fills))
        self.assertAlmostEqual(0.01, sum(fill.quantity for fill in self.fills))

    async def test_trade_through_fills_only_what_better_prices_left(self):
        # A market trade down at 98 is taken by the 1.0 resting at 100
        # before any of it can reach our bid at 99.
        self.rest_book(bids=[(100.0, 1.0), (99.0, 0.0)])
        order = self.create_limit_order(MarketSide.BUY, 99.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 98.0, 0.5)
        )
        self.assertEqual([], self.fills)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 98.0, 1.004)
        )
        self.assertEqual(1, len(self.fills))
        self.assertAlmostEqual(0.004, self.fills[0].quantity)
        self.assertEqual(99.0, self.fills[0].price)

    async def test_trade_through_still_queues_behind_our_own_price(self):
        # Nothing rests at a better price than our bid, but 0.005 sits
        # at the same price and fills ahead of us.
        self.rest_book(bids=[(99.0, 0.005)])
        order = self.create_limit_order(MarketSide.BUY, 99.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 98.0, 0.011)
        )

        self.assertEqual(1, len(self.fills))
        self.assertAlmostEqual(0.006, self.fills[0].quantity)

    async def test_trade_through_of_an_ask_is_capped_by_better_asks(self):
        self.rest_book(asks=[(100.0, 1.0)])
        order = self.create_limit_order(MarketSide.SELL, 101.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 102.0, 1.006)
        )

        self.assertEqual(1, len(self.fills))
        self.assertAlmostEqual(0.006, self.fills[0].quantity)

    async def test_cancel_order_removes_resting_order(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_cancel_order(
            self, CancelOrder(client_order_id=order.client_order_id)
        )
        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.SELL, 100.0, 1.0)
        )

        self.assertEqual(0, len(self.fills))

    async def test_on_order_with_cache(self):
        # Set up test parameters
        symbol = "BTC/USD"
        timestamp = self.mock_order.creation_time.timestamp()

        IDataSource.TRADE_CACHE[(symbol, timestamp)] = [
            Trade(
                exchange_trade_id=1,
                client_order_id="",
                symbol=symbol,
                maker_order_id=str(uuid.uuid4()),
                taker_order_id=str(uuid.uuid4()),
                side=MarketSide.BUY,
                price=50000.0,
                fee=0.0,
                quantity=1.0,
                transaction_time=self.mock_order.creation_time,
            ),
            Trade(
                exchange_trade_id=2,
                client_order_id="",
                symbol=symbol,
                maker_order_id=str(uuid.uuid4()),
                taker_order_id=str(uuid.uuid4()),
                side=MarketSide.SELL,
                price=51000.0,
                fee=0.0,
                quantity=1.0,
                transaction_time=self.mock_order.creation_time,
            ),
        ]

        # Connect and simulate the asynchronous event loop
        self.execution_service.on_order(self, self.mock_order)

        self.assertEqual(len(self.fills), 1)
        self.assertAlmostEqual(
            KrakenFeeSchedule().taker_fee(50000, 0.0001), self.fills[0].fee
        )

    async def test_trades_in_another_symbol_leave_resting_orders_alone(self):
        order = self.create_limit_order(MarketSide.BUY, 100.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self,
            replace(
                self.create_market_trade(MarketSide.SELL, 100.0, 1.0),
                symbol="ETH/USD",
            ),
        )

        self.assertEqual(0, len(self.fills))

    async def test_sell_limit_order_queue_position_delays_fill(self):
        # Someone is displaying 0.02 ahead of us at the ask when we join.
        self.execution_service.on_bbo(
            self,
            BBO(
                symbol="BTC/USD",
                bid_price=99.0,
                bid_quantity=1.0,
                ask_price=100.0,
                ask_quantity=0.02,
            ),
        )
        order = self.create_limit_order(MarketSide.SELL, 100.0)
        self.execution_service.on_order(self, order)

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 100.0, 0.02)
        )
        self.assertEqual(0, len(self.fills))

        self.execution_service.on_market_trade(
            self, self.create_market_trade(MarketSide.BUY, 100.0, 0.01)
        )
        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.01, self.fills[0].quantity)

    async def test_market_order_fills_at_zero_without_a_recent_trade(self):
        self.execution_service.on_order(self, self.mock_order)

        self.assertEqual(1, len(self.fills))
        self.assertEqual(0.0, self.fills[0].price)
