import unittest

from jolteon.market_data.core.bbo import BBO
from jolteon.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)


class TestMidPriceFairPriceModel(unittest.TestCase):
    def test_calculate(self):
        model = MidPriceFairPriceModel()
        bbo = BBO(
            symbol="BTC/USD",
            bid_price=100.0,
            bid_quantity=1.0,
            ask_price=102.0,
            ask_quantity=1.0,
        )

        self.assertEqual(101.0, model.calculate(FairPriceContext(bbo=bbo)))
