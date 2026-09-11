import unittest

from jolteon.engine.market_data.core.book_features import imbalance, vwap
from jolteon.engine.market_data.core.order_book import PriceLevel


class TestImbalance(unittest.TestCase):
    def test_balanced_book(self):
        self.assertEqual(
            0.0,
            imbalance([PriceLevel(100.0, 5.0)], [PriceLevel(101.0, 5.0)]),
        )

    def test_all_size_on_the_bid(self):
        self.assertEqual(1.0, imbalance([PriceLevel(100.0, 5.0)], []))

    def test_all_size_on_the_ask(self):
        self.assertEqual(-1.0, imbalance([], [PriceLevel(101.0, 5.0)]))

    def test_empty_book_abstains(self):
        self.assertEqual(0.0, imbalance([], []))

    def test_zero_quantities_abstain(self):
        self.assertEqual(
            0.0,
            imbalance([PriceLevel(100.0, 0.0)], [PriceLevel(101.0, 0.0)]),
        )

    def test_sums_every_level_given(self):
        bids = [PriceLevel(100.0, 2.0), PriceLevel(99.0, 1.0)]
        asks = [PriceLevel(101.0, 1.0)]

        self.assertEqual(0.5, imbalance(bids, asks))

    def test_depth_is_the_callers_choice(self):
        bids = [PriceLevel(100.0, 1.0), PriceLevel(99.0, 9.0)]
        asks = [PriceLevel(101.0, 1.0), PriceLevel(102.0, 9.0)]

        self.assertEqual(0.0, imbalance(bids[:1], asks[:1]))
        self.assertAlmostEqual(-9 / 11, imbalance(bids[:1], asks))


class TestVwap(unittest.TestCase):
    def setUp(self):
        self.levels = [
            PriceLevel(100.0, 1.0),
            PriceLevel(101.0, 2.0),
            PriceLevel(102.0, 3.0),
        ]

    def test_fills_within_the_first_level(self):
        self.assertEqual(100.0, vwap(self.levels, 0.5))

    def test_walks_across_levels(self):
        self.assertAlmostEqual(100.5, vwap(self.levels, 2.0))

    def test_consumes_the_whole_book(self):
        self.assertAlmostEqual(101.3333333, vwap(self.levels, 6.0), places=6)

    def test_not_enough_size(self):
        self.assertIsNone(vwap(self.levels, 6.5))

    def test_empty_levels(self):
        self.assertIsNone(vwap([], 1.0))

    def test_non_positive_quantity(self):
        self.assertIsNone(vwap(self.levels, 0.0))
        self.assertIsNone(vwap(self.levels, -1.0))
