import unittest
from enum import Enum

from jolteon.core.market import Market


class TestMarketEnum(unittest.TestCase):
    def test_enum_name(self):
        # Setting name and value to be equal to fix an unknown bug that a
        # Market might be implicitly converted to a string.

        self.assertEqual(Market.KRAKEN.value, Market.KRAKEN.name)
        self.assertEqual(Market.COINBASE.value, Market.COINBASE.name)

    def test_buy_enum_value(self):
        self.assertEqual(Market.KRAKEN.value, "KRAKEN")

    def test_sell_enum_value(self):
        self.assertEqual(Market.COINBASE.value, "COINBASE")

    def test_enum_membership(self):
        self.assertTrue(isinstance(Market.KRAKEN, Enum))
        self.assertTrue(isinstance(Market.COINBASE, Enum))

    def test_enum_equality(self):
        self.assertEqual(Market.KRAKEN, Market.KRAKEN)
        self.assertEqual(Market.COINBASE, Market.COINBASE)
        self.assertNotEqual(Market.KRAKEN, Market.COINBASE)

    def test_parse_enum_value(self):
        self.assertEqual(Market.MOCK, Market.parse("MOCK"))
        self.assertEqual(Market.MOCK, Market.parse("mock"))
        self.assertEqual(Market.KRAKEN, Market.parse("KRAKEN"))
        self.assertEqual(Market.KRAKEN, Market.parse("kraken"))
        self.assertEqual(Market.COINBASE, Market.parse("COINBASE"))
        self.assertEqual(Market.COINBASE, Market.parse("coinbase"))

        with self.assertRaises(RuntimeError) as context:
            Market.parse("unknown_market")

        self.assertEqual(
            "Unsupported market unknown_market",
            str(context.exception),
        )
