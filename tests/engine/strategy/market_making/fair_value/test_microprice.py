import unittest

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.microprice import (
    MicropriceAdjustment,
)


class TestMicropriceAdjustment(unittest.TestCase):
    @staticmethod
    def context(bid_quantity: float, ask_quantity: float) -> FairPriceContext:
        return FairPriceContext(
            bbo=BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=bid_quantity,
                ask_price=102.0,
                ask_quantity=ask_quantity,
            )
        )

    def test_name(self):
        self.assertEqual("microprice", MicropriceAdjustment().name)

    def test_balanced_book_adjusts_to_zero(self):
        adjustment = MicropriceAdjustment()

        self.assertEqual(0.0, adjustment.adjustment(self.context(1.0, 1.0)))

    def test_bid_heavy_book_adjusts_upward(self):
        adjustment = MicropriceAdjustment()

        # microprice = (3*102 + 1*100) / 4 = 101.5, mid = 101.0
        self.assertAlmostEqual(
            0.5, adjustment.adjustment(self.context(3.0, 1.0))
        )

    def test_ask_heavy_book_adjusts_downward(self):
        adjustment = MicropriceAdjustment()

        # microprice = (1*102 + 3*100) / 4 = 100.5, mid = 101.0
        self.assertAlmostEqual(
            -0.5, adjustment.adjustment(self.context(1.0, 3.0))
        )

    def test_scale_multiplies_the_raw_adjustment(self):
        adjustment = MicropriceAdjustment(scale=2.0)

        self.assertAlmostEqual(
            1.0, adjustment.adjustment(self.context(3.0, 1.0))
        )

    def test_zero_total_quantity_adjusts_to_zero(self):
        adjustment = MicropriceAdjustment()

        self.assertEqual(0.0, adjustment.adjustment(self.context(0.0, 0.0)))


if __name__ == "__main__":
    unittest.main()
