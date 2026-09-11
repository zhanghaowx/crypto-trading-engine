import unittest

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
    FairPriceAdjustmentSnapshot,
)
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    FairPriceContext,
    FairPriceUpdate,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class StubAdjustment(IFairPriceAdjustment):
    def __init__(self, name: str, value: float):
        self._name = name
        self.value = value

    @property
    def name(self) -> str:
        return self._name

    def adjustment(self, context: FairPriceContext) -> float:
        return self.value


class SubscribingAdjustment(IFairPriceAdjustment):
    """An adjustment sourcing its own view from a signal, rather than
    from FairPriceContext - proves AdjustedFairPriceModel.connect()
    reaches adjustments nested inside its own adjustments list."""

    def __init__(self):
        self.ticks_seen = 0

    @property
    def name(self) -> str:
        return "subscribing"

    def adjustment(self, context: FairPriceContext) -> float:
        return 0.0

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.ticks_seen += 1


class TestAdjustedFairPriceModel(unittest.TestCase):
    def setUp(self):
        self.bbo = BBO(
            symbol="BTC/USD",
            bid_price=100.0,
            bid_quantity=1.0,
            ask_price=102.0,
            ask_quantity=1.0,
        )
        self.context = FairPriceContext(bbo=self.bbo)

    def test_no_adjustments_matches_the_base_model(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(), adjustments=[]
        )

        self.assertEqual(
            FairPrice(bid=101.0, ask=101.0), model.calculate(self.context)
        )

    def test_a_zero_adjustment_matches_the_base_model(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[StubAdjustment("zero", 0.0)],
        )

        self.assertEqual(
            FairPrice(bid=101.0, ask=101.0), model.calculate(self.context)
        )

    def test_adjustments_sum_and_shift_both_sides(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[
                StubAdjustment("a", 0.5),
                StubAdjustment("b", -0.2),
            ],
        )

        self.assertEqual(
            FairPrice(bid=101.3, ask=101.3), model.calculate(self.context)
        )

    def test_max_adjustment_clamps_a_positive_overshoot(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[StubAdjustment("a", 5.0)],
            max_adjustment=1.0,
        )

        self.assertEqual(
            FairPrice(bid=102.0, ask=102.0), model.calculate(self.context)
        )

    def test_max_adjustment_clamps_a_negative_overshoot(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[StubAdjustment("a", -5.0)],
            max_adjustment=1.0,
        )

        self.assertEqual(
            FairPrice(bid=100.0, ask=100.0), model.calculate(self.context)
        )

    def test_max_adjustment_does_not_clamp_a_total_within_bounds(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[StubAdjustment("a", 0.5)],
            max_adjustment=1.0,
        )
        snapshots = list[FairPriceAdjustmentSnapshot]()

        def on_snapshot(_, fair_price_adjustment: FairPriceAdjustmentSnapshot):
            snapshots.append(fair_price_adjustment)

        model.fair_price_adjustment_event.connect(on_snapshot)

        self.assertEqual(
            FairPrice(bid=101.5, ask=101.5), model.calculate(self.context)
        )
        self.assertFalse(snapshots[0].clamped)

    def test_no_max_adjustment_leaves_a_large_total_unclamped(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[StubAdjustment("a", 5.0)],
        )

        self.assertEqual(
            FairPrice(bid=106.0, ask=106.0), model.calculate(self.context)
        )

    def test_emits_a_snapshot_with_the_per_adjustment_breakdown(self):
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(),
            adjustments=[
                StubAdjustment("a", 5.0),
                StubAdjustment("b", -0.5),
            ],
            max_adjustment=1.0,
        )
        snapshots = list[FairPriceAdjustmentSnapshot]()

        def on_snapshot(_, fair_price_adjustment: FairPriceAdjustmentSnapshot):
            snapshots.append(fair_price_adjustment)

        model.fair_price_adjustment_event.connect(on_snapshot)

        model.calculate(self.context)

        self.assertEqual(
            [
                FairPriceAdjustmentSnapshot(
                    symbol="BTC/USD",
                    base_fair_price=101.0,
                    total_adjustment=1.0,
                    clamped=True,
                    adjustments={"a": 5.0, "b": -0.5},
                )
            ],
            snapshots,
        )

    def test_calculate_records_both_the_base_and_composite_models(self):
        base = MidPriceFairPriceModel()
        model = AdjustedFairPriceModel(base=base, adjustments=[])
        updates = list[FairPriceUpdate]()

        def on_update(_, fair_price_update: FairPriceUpdate):
            updates.append(fair_price_update)

        model.fair_price_event.connect(on_update)
        base.fair_price_event.connect(on_update)

        model.calculate(self.context)

        self.assertEqual(
            {"MidPriceFairPriceModel", "AdjustedFairPriceModel"},
            {update.model for update in updates},
        )

    def test_connect_wires_up_a_subscribing_adjustment(self):
        adjustment = SubscribingAdjustment()
        model = AdjustedFairPriceModel(
            base=MidPriceFairPriceModel(), adjustments=[adjustment]
        )

        model.connect()
        signal("ticker_feed").send("mock_sender", bbo=self.bbo)

        self.assertEqual(1, adjustment.ticks_seen)


if __name__ == "__main__":
    unittest.main()
