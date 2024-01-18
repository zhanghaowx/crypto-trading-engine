import unittest
from enum import Enum

from jolteon.core.side import MarketSide


class TestMarketSideEnum(unittest.TestCase):
    def test_enum_name(self):
        # Setting name and value to be equal to fix an unknown bug that a
        # MarketSide might be implicitly converted to a string.

        self.assertEqual(MarketSide.BUY.value, MarketSide.BUY.name)
        self.assertEqual(MarketSide.SELL.value, MarketSide.SELL.name)

    def test_buy_enum_value(self):
        self.assertEqual(MarketSide.BUY.value, "BUY")

    def test_sell_enum_value(self):
        self.assertEqual(MarketSide.SELL.value, "SELL")

    def test_enum_membership(self):
        self.assertTrue(isinstance(MarketSide.BUY, Enum))
        self.assertTrue(isinstance(MarketSide.SELL, Enum))

    def test_enum_equality(self):
        self.assertEqual(MarketSide.BUY, MarketSide.BUY)
        self.assertEqual(MarketSide.SELL, MarketSide.SELL)
        self.assertNotEqual(MarketSide.BUY, MarketSide.SELL)
