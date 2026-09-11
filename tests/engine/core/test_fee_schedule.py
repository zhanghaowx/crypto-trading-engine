import unittest

from jolteon.engine.core.fee_schedule import KRAKEN, FeeSchedule


class TestFeeSchedule(unittest.TestCase):
    def setUp(self):
        self.fees = FeeSchedule(maker_rate=0.001, taker_rate=0.002)

    def test_charges_each_rate_against_the_notional(self):
        self.assertAlmostEqual(0.2, self.fees.maker_fee(100.0, 2.0))
        self.assertAlmostEqual(0.4, self.fees.taker_fee(100.0, 2.0))

    def test_kraken_charges_base_tier_rates(self):
        self.assertAlmostEqual(0.0025, KRAKEN.maker_rate)
        self.assertAlmostEqual(0.0040, KRAKEN.taker_rate)

    def test_kraken_charges_a_maker_less_than_a_taker(self):
        self.assertLess(KRAKEN.maker_rate, KRAKEN.taker_rate)
