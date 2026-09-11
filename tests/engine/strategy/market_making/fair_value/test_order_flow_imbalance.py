import unittest
from datetime import datetime

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.order_flow_imbalance import (  # noqa: E501
    OrderFlowImbalanceAdjustment,
)


class TestOrderFlowImbalanceAdjustment(unittest.TestCase):
    def setUp(self):
        self.adjustment = OrderFlowImbalanceAdjustment()

    @staticmethod
    def context(bids, asks) -> FairPriceContext:
        order_book = OrderBook("BTC/USD")
        order_book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(price, qty) for price, qty in bids],
                asks=[PriceLevel(price, qty) for price, qty in asks],
                is_snapshot=True,
                exchange_time=datetime(2024, 1, 1),
            )
        )
        bbo = order_book.bbo()
        assert bbo is not None
        return FairPriceContext(bbo=bbo, order_book=order_book)

    def test_abstains_without_depth(self):
        bbo = BBO(
            symbol="BTC/USD",
            bid_price=99.0,
            bid_quantity=1.0,
            ask_price=101.0,
            ask_quantity=1.0,
        )

        self.assertEqual(
            0.0, self.adjustment.adjustment(FairPriceContext(bbo=bbo))
        )

    def test_a_balanced_book_does_not_move_fair_price(self):
        context = self.context([(99.0, 1.0)], [(101.0, 1.0)])

        self.assertEqual(0.0, self.adjustment.adjustment(context))

    def test_resting_bids_lift_fair_price(self):
        context = self.context([(99.0, 3.0)], [(101.0, 1.0)])

        self.assertAlmostEqual(0.5, self.adjustment.adjustment(context))

    def test_resting_asks_push_fair_price_down(self):
        context = self.context([(99.0, 1.0)], [(101.0, 3.0)])

        self.assertAlmostEqual(-0.5, self.adjustment.adjustment(context))

    def test_a_one_sided_book_moves_by_one_half_spread(self):
        """
        The touch can outlive one side of the book, since BBO also comes
        from the ticker channel. The shift stays bounded there.
        """
        context = self.context([(99.0, 1.0)], [(101.0, 1.0)])
        context.order_book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[],
                asks=[PriceLevel(101.0, 0.0)],
                is_snapshot=False,
                exchange_time=datetime(2024, 1, 1),
            )
        )

        self.assertAlmostEqual(1.0, self.adjustment.adjustment(context))

    def test_scale_caps_the_shift(self):
        adjustment = OrderFlowImbalanceAdjustment(scale=0.5)
        context = self.context([(99.0, 3.0)], [(101.0, 1.0)])

        self.assertAlmostEqual(0.25, adjustment.adjustment(context))

    def test_depth_bounds_what_is_counted(self):
        bids = [(99.0, 1.0), (98.0, 100.0)]
        asks = [(101.0, 1.0)]

        shallow = OrderFlowImbalanceAdjustment(depth=1)
        self.assertEqual(0.0, shallow.adjustment(self.context(bids, asks)))

        deep = OrderFlowImbalanceAdjustment(depth=2)
        self.assertGreater(deep.adjustment(self.context(bids, asks)), 0.9)

    def test_depth_must_be_positive(self):
        with self.assertRaises(AssertionError):
            OrderFlowImbalanceAdjustment(depth=0)

    def test_is_recorded_under_its_own_name(self):
        self.assertEqual("order_flow_imbalance", self.adjustment.name)
