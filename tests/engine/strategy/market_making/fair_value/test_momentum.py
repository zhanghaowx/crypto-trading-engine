import unittest
from datetime import datetime

import pytz

from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.strategy.market_making.fair_value.momentum import (
    MomentumAdjustment,
)


class TestMomentumAdjustment(unittest.TestCase):
    def setUp(self):
        self.context = BookSnapshot(
            bbo=BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=1.0,
                ask_price=102.0,
                ask_quantity=1.0,
            )
        )

    @staticmethod
    def trade(side: MarketSide, quantity: float = 1.0) -> Trade:
        return Trade(
            trade_id=0,
            client_order_id="",
            symbol="BTC/USD",
            maker_order_id="",
            taker_order_id="",
            side=side,
            price=101.0,
            fee=0.0,
            quantity=quantity,
            transaction_time=datetime(2024, 1, 1, tzinfo=pytz.utc),
        )

    def test_name(self):
        self.assertEqual("momentum", MomentumAdjustment().name)

    def test_returns_zero_before_min_trades_seen(self):
        adjustment = MomentumAdjustment(min_trades=3)

        adjustment.on_trade("_", self.trade(MarketSide.BUY))
        adjustment.on_trade("_", self.trade(MarketSide.BUY))

        self.assertEqual(0.0, adjustment.adjustment(self.context))

    def test_ewma_computes_the_expected_flow(self):
        adjustment = MomentumAdjustment(decay=0.5, min_trades=1)

        adjustment.on_trade("_", self.trade(MarketSide.BUY, quantity=1.0))
        self.assertAlmostEqual(0.5, adjustment.adjustment(self.context))

        adjustment.on_trade("_", self.trade(MarketSide.SELL, quantity=1.0))
        self.assertAlmostEqual(-0.25, adjustment.adjustment(self.context))

    def test_a_run_of_buys_adjusts_upward(self):
        adjustment = MomentumAdjustment(decay=0.5, min_trades=1)

        for _ in range(10):
            adjustment.on_trade("_", self.trade(MarketSide.BUY))

        self.assertGreater(adjustment.adjustment(self.context), 0.0)

    def test_a_run_of_sells_adjusts_downward(self):
        adjustment = MomentumAdjustment(decay=0.5, min_trades=1)

        for _ in range(10):
            adjustment.on_trade("_", self.trade(MarketSide.SELL))

        self.assertLess(adjustment.adjustment(self.context), 0.0)

    def test_scale_multiplies_the_flow(self):
        adjustment = MomentumAdjustment(scale=2.0, decay=0.0, min_trades=1)

        adjustment.on_trade("_", self.trade(MarketSide.BUY, quantity=3.0))

        self.assertAlmostEqual(6.0, adjustment.adjustment(self.context))


if __name__ == "__main__":
    unittest.main()
