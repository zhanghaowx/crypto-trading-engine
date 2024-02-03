import math
import unittest
import uuid
from datetime import datetime
from typing import Union
from unittest.mock import Mock

import pytz

from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.execution.coinbase.mock_execution_service import (
    MockExecutionService,
)
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade


class TestMockExecutionService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.execution_service = MockExecutionService(
            api_key="api_key", api_secret="api_secret"
        )
        self.execution_service._client = Mock()
        self.execution_service._client.get_product_book.return_value = {
            "pricebook": {
                "product_id": "BTC-USD",
                "bids": [
                    {"price": "99.5", "size": "2.0"},
                    {"price": "99.0", "size": "1.0"},
                ],
                "asks": [
                    {"price": "100.5", "size": "1.0"},
                    {"price": "101.0", "size": "2.0"},
                ],
            }
        }
        self.execution_service._client.get_market_trades.return_value = {
            "trades": [
                {
                    "trade_id": "001",
                    "product_id": "BTC-USD",
                    "price": "150",
                    "size": "4",
                    "time": "2021-05-31T09:59:59Z",
                    "side": "BUY",
                    "bid": "291.13",
                    "ask": "292.40",
                }
            ],
            "best_bid": "291.13",
            "best_ask": "292.40",
        }
        self.fills = list[Trade]()

        # Subscribe to signals

        self.execution_service.order_fill_event.connect(self.on_order_fill)

    def buy(self, symbol: str, price: Union[float, None], quantity: float):
        """
        Place a buy order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            symbol: Symbol of the product to buy
            price: Price of the product to buy
            quantity: Quantity of the product to buy

        Returns:
            None
        """
        buy_order_id = str(uuid.uuid4())
        buy_order = Order(
            client_order_id=buy_order_id,
            order_type=OrderType.MARKET_ORDER,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=MarketSide.BUY,
            creation_time=datetime.now(pytz.utc),
        )
        self.execution_service.on_order("unittest", buy_order)

    def sell(self, symbol: str, price: Union[float, None], quantity: float):
        """
        Place a sell order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            symbol: Symbol of the product to sell
            price: Price of the product to sell
            quantity: Quantity of the product to sell

        Returns:
            None

        """
        sell_order_id = str(uuid.uuid4())
        sell_order = Order(
            client_order_id=sell_order_id,
            order_type=OrderType.MARKET_ORDER,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=MarketSide.SELL,
            creation_time=datetime.now(pytz.utc),
        )
        self.execution_service.on_order("unittest", sell_order)

    def on_order_fill(self, _: str, trade: Trade):
        """
        Stores the order fill for verification
        Args:
            _: Name of the sender
            trade: Details about the trade

        Returns:
            None
        """
        self.fills.append(trade)

    async def test_buy(self):
        # Execute
        self.buy(symbol="BTC-USD", price=100.0, quantity=1.0)
        self.assertEqual(0, len(self.fills))

        self.buy(symbol="BTC-USD", price=100.5, quantity=0.1)
        self.assertEqual(1, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(100.5, self.fills[-1].price)
        self.assertEqual(0.1, self.fills[-1].quantity)

        self.buy(symbol="BTC-USD", price=100.6, quantity=0.2)
        self.assertEqual(2, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(100.5, self.fills[-1].price)
        self.assertEqual(0.2, self.fills[-1].quantity)

        self.buy(symbol="BTC-USD", price=110.0, quantity=10)
        self.assertEqual(4, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(101.0, self.fills[-1].price)
        self.assertEqual(2.0, self.fills[-1].quantity)
        self.assertEqual("BTC-USD", self.fills[-2].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-2].side)
        self.assertEqual(100.5, self.fills[-2].price)
        self.assertEqual(1.0, self.fills[-2].quantity)

    async def test_buy_with_market_order(self):
        # Execute
        self.buy(symbol="BTC-USD", price=None, quantity=0.1)
        self.assertEqual(1, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(100.5, self.fills[-1].price)
        self.assertEqual(0.1, self.fills[-1].quantity)

        self.buy(symbol="BTC-USD", price=None, quantity=0.2)
        self.assertEqual(2, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(100.5, self.fills[-1].price)
        self.assertEqual(0.2, self.fills[-1].quantity)

        self.buy(symbol="BTC-USD", price=None, quantity=10)
        self.assertEqual(4, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-1].side)
        self.assertEqual(101.0, self.fills[-1].price)
        self.assertEqual(2.0, self.fills[-1].quantity)
        self.assertEqual("BTC-USD", self.fills[-2].symbol)
        self.assertEqual(MarketSide.BUY, self.fills[-2].side)
        self.assertEqual(100.5, self.fills[-2].price)
        self.assertEqual(1.0, self.fills[-2].quantity)

    async def test_sell(self):
        # Execute
        self.sell(symbol="BTC-USD", price=100.0, quantity=1.0)
        self.assertEqual(0, len(self.fills))

        self.sell(symbol="BTC-USD", price=99.5, quantity=0.1)
        self.assertEqual(1, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.5, self.fills[-1].price)
        self.assertEqual(0.1, self.fills[-1].quantity)

        self.sell(symbol="BTC-USD", price=99.4, quantity=0.2)
        self.assertEqual(2, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.5, self.fills[-1].price)
        self.assertEqual(0.2, self.fills[-1].quantity)

        self.sell(symbol="BTC-USD", price=98.0, quantity=10)
        self.assertEqual(4, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.0, self.fills[-1].price)
        self.assertEqual(1.0, self.fills[-1].quantity)
        self.assertEqual("BTC-USD", self.fills[-2].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-2].side)
        self.assertEqual(99.5, self.fills[-2].price)
        self.assertEqual(2.0, self.fills[-2].quantity)

    async def test_sell_with_market_order(self):
        # Execute
        self.sell(symbol="BTC-USD", price=None, quantity=0.1)
        self.assertEqual(1, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.5, self.fills[-1].price)
        self.assertEqual(0.1, self.fills[-1].quantity)

        self.sell(symbol="BTC-USD", price=None, quantity=0.2)
        self.assertEqual(2, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.5, self.fills[-1].price)
        self.assertEqual(0.2, self.fills[-1].quantity)

        self.sell(symbol="BTC-USD", price=None, quantity=10)
        self.assertEqual(4, len(self.fills))
        self.assertEqual("BTC-USD", self.fills[-1].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-1].side)
        self.assertEqual(99.0, self.fills[-1].price)
        self.assertEqual(1.0, self.fills[-1].quantity)
        self.assertEqual("BTC-USD", self.fills[-2].symbol)
        self.assertEqual(MarketSide.SELL, self.fills[-2].side)
        self.assertEqual(99.5, self.fills[-2].price)
        self.assertEqual(2.0, self.fills[-2].quantity)

    async def test_short_sell(self):
        order = Order(
            client_order_id=str(id_generator().next()),
            order_type=OrderType.MARKET_ORDER,
            symbol="BTC-USD",
            price=1.0,
            quantity=1.0,
            side="SHORT_SELL",
            creation_time=datetime.now(pytz.utc),
        )
        with self.assertRaises(AssertionError) as context:
            self.execution_service.on_order("unittest", order)

        self.assertEqual(
            "'SHORT_SELL' is not a valid MarketSide",
            str(context.exception),
        )

    async def test_replay_buy(self):
        with time_manager() as manager:
            manager.use_fake_time(datetime.now(pytz.utc), self)

            # Execute
            self.buy(symbol="BTC-USD", price=100.0, quantity=1.0)
            self.assertEqual(1, len(self.fills))
            self.assertEqual("BTC-USD", self.fills[-1].symbol)
            self.assertEqual(MarketSide.BUY, self.fills[-1].side)
            self.assertEqual(150.0, self.fills[-1].price)
            self.assertEqual(1.0, self.fills[-1].quantity)

    async def test_replay_sell(self):
        with time_manager() as manager:
            manager.use_fake_time(datetime.now(pytz.utc), self)

            # Execute
            self.sell(symbol="BTC-USD", price=100.0, quantity=1.0)
            self.assertEqual(1, len(self.fills))
            self.assertEqual("BTC-USD", self.fills[-1].symbol)
            self.assertEqual(MarketSide.SELL, self.fills[-1].side)
            self.assertEqual(150.0, self.fills[-1].price)
            self.assertEqual(1.0, self.fills[-1].quantity)

    async def test_replay_sell_getting_invalid_market_trade(self):
        with time_manager() as manager:
            manager.use_fake_time(datetime.now(pytz.utc), self)

            self.execution_service._client.get_market_trades.return_value = {
                "trades": [
                    {
                        "trade_id": "ABC",
                        "product_id": "BTC-USD",
                        "price": "ABC",
                        "size": "4",
                        "time": "2021-05-31T09:59:59Z",
                        "side": "UNKNOWN",
                        "bid": "",
                        "ask": "",
                    },
                    {
                        "trade_id": "001",
                        "product_id": "BTC-USD",
                        "price": "160",
                        "size": "4",
                        "time": "2021-05-31T09:59:59Z",
                        "side": "BUY",
                        "bid": "291.13",
                        "ask": "292.40",
                    },
                ],
                "best_bid": "291.13",
                "best_ask": "292.40",
            }
            self.sell(symbol="BTC-USD", price=100.0, quantity=1.0)
            self.assertEqual(1, len(self.fills))
            self.assertEqual("BTC-USD", self.fills[-1].symbol)
            self.assertEqual(MarketSide.SELL, self.fills[-1].side)
            self.assertEqual(160.0, self.fills[-1].price)
            self.assertEqual(1.0, self.fills[-1].quantity)

    async def test_replay_sell_getting_no_valid_market_trade(self):
        with time_manager() as manager:
            manager.use_fake_time(datetime.now(pytz.utc), self)

            self.execution_service._client.get_market_trades.return_value = {
                "trades": [
                    {
                        "trade_id": "ABC",
                        "product_id": "BTC-USD",
                        "price": "ABC",
                        "size": "4",
                        "time": "2021-05-31T09:59:59Z",
                        "side": "UNKNOWN",
                        "bid": "",
                        "ask": "",
                    },
                ],
                "best_bid": "291.13",
                "best_ask": "292.40",
            }
            self.sell(symbol="BTC-USD", price=100.0, quantity=1.0)
            self.assertEqual(1, len(self.fills))
            self.assertEqual("BTC-USD", self.fills[-1].symbol)
            self.assertEqual(MarketSide.SELL, self.fills[-1].side)
            self.assertEqual(True, math.isnan(self.fills[-1].price))
            self.assertEqual(1.0, self.fills[-1].quantity)
