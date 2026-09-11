import unittest
from enum import Enum

from jolteon.engine.core.market import Market


class TestMarketEnum(unittest.TestCase):
    def test_enum_name(self):
        # Setting name and value to be equal to fix an unknown bug that a
        # Market might be implicitly converted to a string.

        self.assertEqual(Market.KRAKEN.value, Market.KRAKEN.name)
        self.assertEqual(Market.MOCK.value, Market.MOCK.name)

    def test_buy_enum_value(self):
        self.assertEqual(Market.KRAKEN.value, "KRAKEN")

    def test_sell_enum_value(self):
        self.assertEqual(Market.MOCK.value, "MOCK")

    def test_enum_membership(self):
        self.assertTrue(isinstance(Market.KRAKEN, Enum))
        self.assertTrue(isinstance(Market.MOCK, Enum))

    def test_enum_equality(self):
        self.assertEqual(Market.KRAKEN, Market.KRAKEN)
        self.assertEqual(Market.MOCK, Market.MOCK)
        self.assertNotEqual(Market.KRAKEN, Market.MOCK)

    def test_parse_enum_value(self):
        self.assertEqual(Market.MOCK, Market.parse("MOCK"))
        self.assertEqual(Market.MOCK, Market.parse("mock"))
        self.assertEqual(Market.KRAKEN, Market.parse("KRAKEN"))
        self.assertEqual(Market.KRAKEN, Market.parse("kraken"))

        with self.assertRaises(RuntimeError) as context:
            Market.parse("unknown_market")

        self.assertEqual(
            "Unsupported market unknown_market",
            str(context.exception),
        )
