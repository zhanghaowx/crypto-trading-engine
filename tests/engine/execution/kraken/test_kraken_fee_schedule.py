import unittest

from jolteon.engine.execution.kraken.fee_schedule import (
    CRYPTO_PAIR_TIERS,
    STABLECOIN_PAIR_TIERS,
    KrakenFeeSchedule,
)


class TestKrakenFeeSchedule(unittest.TestCase):
    def test_an_untraded_account_pays_the_base_tier(self):
        fees = KrakenFeeSchedule()

        self.assertAlmostEqual(0.0040, fees.maker_rate)
        self.assertAlmostEqual(0.0080, fees.taker_rate)

    def test_volume_buys_a_cheaper_tier(self):
        fees = KrakenFeeSchedule(thirty_day_volume=300_000.0)

        self.assertAlmostEqual(0.0010, fees.maker_rate)
        self.assertAlmostEqual(0.0022, fees.taker_rate)

    def test_volume_between_tiers_keeps_the_one_already_reached(self):
        self.assertEqual(
            KrakenFeeSchedule(thirty_day_volume=250_000.0).maker_rate,
            KrakenFeeSchedule(thirty_day_volume=499_999.0).maker_rate,
        )

    def test_the_top_tier_makes_a_maker_free(self):
        fees = KrakenFeeSchedule(thirty_day_volume=50_000_000.0)

        self.assertEqual(0.0, fees.maker_rate)
        self.assertAlmostEqual(0.0010, fees.taker_rate)

    def test_a_stablecoin_pair_is_charged_from_its_own_schedule(self):
        fees = KrakenFeeSchedule(stablecoin_pair=True)

        self.assertAlmostEqual(0.0020, fees.maker_rate)
        self.assertAlmostEqual(0.0020, fees.taker_rate)

    def test_charges_the_rate_against_the_notional(self):
        fees = KrakenFeeSchedule()

        self.assertAlmostEqual(0.2, fees.maker_fee(50_000.0, 0.001))
        self.assertAlmostEqual(0.4, fees.taker_fee(50_000.0, 0.001))

    def test_every_tier_charges_a_maker_no_more_than_a_taker(self):
        for tier in CRYPTO_PAIR_TIERS + STABLECOIN_PAIR_TIERS:
            with self.subTest(volume=tier.minimum_volume):
                self.assertLessEqual(tier.maker_rate, tier.taker_rate)

    def test_tiers_only_ever_get_cheaper_as_volume_rises(self):
        for tiers in (CRYPTO_PAIR_TIERS, STABLECOIN_PAIR_TIERS):
            for cheaper, dearer in zip(tiers[1:], tiers):
                with self.subTest(volume=cheaper.minimum_volume):
                    self.assertGreater(
                        cheaper.minimum_volume, dearer.minimum_volume
                    )
                    self.assertLessEqual(cheaper.maker_rate, dearer.maker_rate)
                    self.assertLessEqual(cheaper.taker_rate, dearer.taker_rate)
