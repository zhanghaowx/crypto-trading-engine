import unittest
import uuid
from datetime import datetime
from random import randint

import pytz

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.position.position_manager import PositionManager


def randomInt(param, param1):
    pass


class TestPositionManager(unittest.IsolatedAsyncioTestCase):
    def create_trade(
        self,
        market_side: MarketSide,
        symbol: str,
        price: float,
        quantity: float,
    ):
        return Trade(
            trade_id=randint(1, 1000),
            sequence_number=randint(1, 1000),
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=market_side,
            price=price,
            quantity=quantity,
            transaction_time=datetime.now(pytz.utc),
        )

    async def test_buy(self):
        position_manager = PositionManager()

        def buy(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_", self.create_trade(MarketSide.BUY, symbol, price, quantity)
            )

        buy("BTC", 1.5, 2.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(2.0, position_manager.positions["BTC"].volume)
        self.assertEqual(3.0, position_manager.positions["BTC"].cash_value)

        buy("BTC", 2.0, 5.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)

        buy("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(5.0, position_manager.positions["ETH"].volume)
        self.assertEqual(10.0, position_manager.positions["ETH"].cash_value)

    async def test_sell(self):
        position_manager = PositionManager()

        def buy(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_", self.create_trade(MarketSide.BUY, symbol, price, quantity)
            )

        def sell(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_",
                self.create_trade(MarketSide.SELL, symbol, price, quantity),
            )

        buy("BTC", 1.5, 100.0)
        buy("ETH", 2.5, 1000.0)

        sell("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(995.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2490.0, position_manager.positions["ETH"].cash_value)

        sell("ETH", 1.0, 10.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)

        sell("BTC", 0.5, 20.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(80.0, position_manager.positions["BTC"].volume)
        self.assertEqual(140.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)

    def test_on_fill_invalid_side(self):
        trade = self.create_trade("invalid", "BTC-USD", 100.0, 1.0)

        with self.assertRaises(AssertionError) as context:
            position_manager = PositionManager()
            position_manager.on_fill("_", trade)

        self.assertRaisesRegex(
            AssertionError,
            "^Trade has an invalid trade side",
        )
