import unittest

from jolteon.engine.execution.binance_us.fee_schedule import (
    SPOT_TIERS,
    BinanceUsFeeSchedule,
)


class TestBinanceUsFeeSchedule(unittest.TestCase):
    def test_an_untraded_account_pays_the_base_tier(self):
        fees = BinanceUsFeeSchedule()

        self.assertEqual(0.0, fees.maker_rate)
        self.assertAlmostEqual(0.000200, fees.taker_rate)

    def test_volume_halves_the_taker_rate(self):
        fees = BinanceUsFeeSchedule(thirty_day_volume=500_000_000.0)

        self.assertEqual(0.0, fees.maker_rate)
        self.assertAlmostEqual(0.000100, fees.taker_rate)

    def test_volume_below_the_threshold_keeps_the_base_tier(self):
        fees = BinanceUsFeeSchedule(thirty_day_volume=499_999_999.0)

        self.assertAlmostEqual(0.000200, fees.taker_rate)

    def test_a_maker_is_free_at_every_volume(self):
        for volume in (0.0, 1_000.0, 500_000_000.0, 10_000_000_000.0):
            with self.subTest(volume=volume):
                fees = BinanceUsFeeSchedule(thirty_day_volume=volume)
                self.assertEqual(0.0, fees.maker_fee(50_000.0, 1.0))

    def test_charges_the_rate_against_the_notional(self):
        fees = BinanceUsFeeSchedule()

        self.assertAlmostEqual(0.01, fees.taker_fee(50_000.0, 0.001))

    def test_every_tier_charges_a_maker_no_more_than_a_taker(self):
        for tier in SPOT_TIERS:
            with self.subTest(volume=tier.minimum_volume):
                self.assertLessEqual(tier.maker_rate, tier.taker_rate)

    def test_tiers_only_ever_get_cheaper_as_volume_rises(self):
        for cheaper, dearer in zip(SPOT_TIERS[1:], SPOT_TIERS):
            with self.subTest(volume=cheaper.minimum_volume):
                self.assertGreater(
                    cheaper.minimum_volume, dearer.minimum_volume
                )
                self.assertLessEqual(cheaper.maker_rate, dearer.maker_rate)
                self.assertLessEqual(cheaper.taker_rate, dearer.taker_rate)
