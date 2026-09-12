import unittest

from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.position.position_manager import PositionUpdate
from jolteon.engine.strategy.market_making.fair_value.inventory import (
    InventoryAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    InventoryAdjustmentParameters,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)


class TestInventoryAdjustment(unittest.TestCase):
    @staticmethod
    def context(symbol: str = "BTC/USD") -> BookSnapshot:
        return BookSnapshot(
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
        adjustment = InventoryAdjustment(scale=1.0)

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=2.0)
        )

        self.assertEqual(-2.0, adjustment.adjustment(self.context()))

    def test_short_position_adjusts_upward(self):
        adjustment = InventoryAdjustment(scale=1.0)

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=-2.0)
        )

        self.assertEqual(2.0, adjustment.adjustment(self.context()))

    def test_a_full_position_skews_by_exactly_the_declared_skew(self):
        service = StaticParameterService(
            MarketMakingParameters(max_inventory=0.01),
            InventoryAdjustmentParameters(skew_at_max_inventory=5.0),
        )
        adjustment = InventoryAdjustment(parameter_service=service)

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=0.01)
        )

        self.assertAlmostEqual(-5.0, adjustment.adjustment(self.context()))

    def test_raising_the_cap_carries_the_skew_with_it(self):
        """
        The skew is stated against the cap, so the two cannot drift: a
        larger cap must still skew by the same amount at a full
        position, and by proportionally less below it.
        """
        adjustment = InventoryAdjustment(
            parameter_service=StaticParameterService(
                MarketMakingParameters(max_inventory=0.02),
                InventoryAdjustmentParameters(skew_at_max_inventory=5.0),
            )
        )

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=0.01)
        )
        self.assertAlmostEqual(-2.5, adjustment.adjustment(self.context()))

        adjustment.on_position_updated(
            "_", PositionUpdate(symbol="BTC/USD", volume=0.02)
        )
        self.assertAlmostEqual(-5.0, adjustment.adjustment(self.context()))

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
