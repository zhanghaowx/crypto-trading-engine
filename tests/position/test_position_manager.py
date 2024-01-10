import unittest

from crypto_trading_engine.position.position_manager import PositionManager


class TestPositionManager(unittest.IsolatedAsyncioTestCase):
    async def test_buy(self):
        position_manager = PositionManager()
        position_manager.on_buy("BTC", 1.5, 2.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(2.0, position_manager.positions["BTC"].volume)
        self.assertEqual(3.0, position_manager.positions["BTC"].cash_value)

        position_manager.on_buy("BTC", 2.0, 5.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)

        position_manager.on_buy("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(5.0, position_manager.positions["ETH"].volume)
        self.assertEqual(10.0, position_manager.positions["ETH"].cash_value)

    async def test_sell(self):
        position_manager = PositionManager()
        position_manager.on_buy("BTC", 1.5, 100.0)
        position_manager.on_buy("ETH", 2.5, 1000.0)

        position_manager.on_sell("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(995.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2490.0, position_manager.positions["ETH"].cash_value)

        position_manager.on_sell("ETH", 1.0, 10.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)

        position_manager.on_sell("BTC", 0.5, 20.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(80.0, position_manager.positions["BTC"].volume)
        self.assertEqual(140.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)
