import unittest

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class StubAdjustment(IFairPriceAdjustment):
    def __init__(self, name: str, value: float):
        self._name = name
        self._value = value

    @property
    def name(self) -> str:
        return self._name

    def adjustment(self, context: FairPriceContext) -> float:
        return self._value


class TestIFairPriceAdjustment(unittest.TestCase):
    def test_subclass_reports_its_name_and_adjustment(self):
        adjustment = StubAdjustment("stub", 1.5)
        context = FairPriceContext(
            bbo=BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=1.0,
                ask_price=102.0,
                ask_quantity=1.0,
            )
        )

        self.assertEqual("stub", adjustment.name)
        self.assertEqual(1.5, adjustment.adjustment(context))


if __name__ == "__main__":
    unittest.main()
