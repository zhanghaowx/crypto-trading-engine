import unittest

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.position.position_manager import PositionUpdate
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.inventory import (
    InventoryAdjustment,
)


class TestInventoryAdjustment(unittest.TestCase):
    @staticmethod
    def context(symbol: str = "BTC/USD") -> FairPriceContext:
        return FairPriceContext(
            bbo=BBO(
                symbol=symbol,
                bid_price=100.0,
                bid_quantity=1.0,
                ask_price=102.0,
                ask_quantity=1.0,
            )
        )

    def test_name(self):
        self.assertEqual("inventory", InventoryAdjustment().name)

    def test_flat_position_adjusts_to_zero(self):
        adjustment = InventoryAdjustment()

        self.assertEqual(0.0, adjustment.adjustment(self.context()))

    def test_long_position_adjusts_downward(self):
        adjustment = InventoryAdjustment()

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=2.0)
        )

        self.assertEqual(-2.0, adjustment.adjustment(self.context()))

    def test_short_position_adjusts_upward(self):
        adjustment = InventoryAdjustment()

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=-2.0)
        )

        self.assertEqual(2.0, adjustment.adjustment(self.context()))

    def test_scale_multiplies_the_adjustment(self):
        adjustment = InventoryAdjustment(scale=0.5)

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=2.0)
        )

        self.assertEqual(-1.0, adjustment.adjustment(self.context()))

    def test_tracks_symbols_independently(self):
        adjustment = InventoryAdjustment()

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=2.0)
        )

        self.assertEqual(0.0, adjustment.adjustment(self.context("ETH/USD")))


if __name__ == "__main__":
    unittest.main()
