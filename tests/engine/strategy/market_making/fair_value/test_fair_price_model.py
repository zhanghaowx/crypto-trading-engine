import unittest

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    FairPriceContext,
    FairPriceUpdate,
    IFairPriceModel,
)


class StubFairPriceModel(IFairPriceModel):
    def _calculate(self, context: FairPriceContext) -> FairPrice:
        return FairPrice(bid=1.0, ask=2.0)


class TestIFairPriceModel(unittest.TestCase):
    def setUp(self):
        self.bbo = BBO(
            symbol="BTC/USD",
            bid_price=100.0,
            bid_quantity=1.0,
            ask_price=102.0,
            ask_quantity=1.0,
        )
        self.updates = list[FairPriceUpdate]()

    def _record(self, model: IFairPriceModel) -> None:
        def on_fair_price(_, fair_price_update: FairPriceUpdate):
            self.updates.append(fair_price_update)

        model.fair_price_event.connect(on_fair_price)
        self.addCleanup(model.fair_price_event.disconnect, on_fair_price)

    def test_calculate_returns_what_the_subclass_computed(self):
        model = StubFairPriceModel()

        self.assertEqual(
            FairPrice(bid=1.0, ask=2.0),
            model.calculate(FairPriceContext(bbo=self.bbo)),
        )

    def test_update_names_the_emitting_model(self):
        model = StubFairPriceModel()
        self._record(model)

        model.calculate(FairPriceContext(bbo=self.bbo))

        self.assertEqual(
            [
                FairPriceUpdate(
                    symbol="BTC/USD",
                    model="StubFairPriceModel",
                    bid_fair_price=1.0,
                    ask_fair_price=2.0,
                )
            ],
            self.updates,
        )


if __name__ == "__main__":
    unittest.main()
