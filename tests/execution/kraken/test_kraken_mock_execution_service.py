import uuid
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

import pytz

from jolteon.core.side import MarketSide
from jolteon.execution.kraken.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.core.order import Order, OrderType
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
