import unittest

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    FairPriceContext,
    FairPriceUpdate,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
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

        self.assertEqual(
            FairPrice(bid=101.0, ask=101.0),
            model.calculate(FairPriceContext(bbo=bbo)),
        )

    def test_calculate_emits_fair_price_signal(self):
        model = MidPriceFairPriceModel()
        bbo = BBO(
            symbol="BTC/USD",
            bid_price=100.0,
            bid_quantity=1.0,
            ask_price=102.0,
            ask_quantity=1.0,
        )
        updates = list[FairPriceUpdate]()

        def on_fair_price(_, fair_price_update: FairPriceUpdate):
            updates.append(fair_price_update)

        model.fair_price_event.connect(on_fair_price)

        model.calculate(FairPriceContext(bbo=bbo))

        self.assertEqual(
            [
                FairPriceUpdate(
                    symbol="BTC/USD",
                    model="MidPriceFairPriceModel",
                    bid_fair_price=101.0,
                    ask_fair_price=101.0,
                )
            ],
            updates,
        )
