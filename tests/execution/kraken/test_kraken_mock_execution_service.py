import uuid
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

import pytz

from jolteon.core.side import MarketSide
from jolteon.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.data_source import IDataSource


class TestMockExecutionService(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fills = list[Trade]()
        self.execution_service = MockExecutionService()
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

    async def test_on_order(self):
        # Set up test parameters
        symbol = "BTC/USD"
        timestamp = self.mock_order.creation_time.timestamp()

        # Mock the requests.get method to return a custom JSON response
        mock_response = {
            "error": [],
            "result": {
                symbol: [
                    [50000.0, 1.0, timestamp, "b", "m", "", 1],
                    [51000.0, 1.0, timestamp, "s", "l", "", 2],
                    # Add more simulated trades as needed
                ],
                "last": timestamp,  # Mock the last timestamp
            },
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            # Set the return value of the mock to the custom JSON response
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            # Connect and simulate the asynchronous event loop
            self.execution_service.on_order(self, self.mock_order)

        self.assertEqual(len(self.fills), 1)
        self.assertEqual(self.fills[0].fee, 50000 * 0.0001 * 0.0026)

    @staticmethod
    def create_market_trade(side: MarketSide, price: float, quantity: float):
        return Trade(
            trade_id=1,
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
                trade_id=1,
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
                trade_id=2,
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
        self.assertEqual(self.fills[0].fee, 50000 * 0.0001 * 0.0026)
