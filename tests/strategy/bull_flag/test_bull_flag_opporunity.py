import math
import unittest
from datetime import datetime, timedelta
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.strategy.bull_flag.bull_flag_opportunity import (
    BullFlagOpportunity,
)


class TestBullFlagOpportunity(unittest.TestCase):
    def setUp(self):
        self.start_time = datetime(2024, 1, 1, 0, 0, 0)
        self.end_time = datetime(2024, 1, 2, 0, 0, 0)
        self.candlestick = Candlestick(
            self.start_time,
            duration_in_seconds=60,
            open=100,
            high=101,
            low=99,
            close=100,
        )
        self.params = Parameters()

    def test_set_bull_flag(self):
        opportunity = BullFlagOpportunity(
            start=self.start_time, end=self.end_time
        )
        self.assertEqual(opportunity.bull_flag_open_close, 0.0)
        self.assertEqual(opportunity.bull_flag_return_pct, 0.0)

        # Set bull flag using a sample candlestick
        self.candlestick.close = 110
        self.candlestick.open = 100
        opportunity.set_bull_flag(self.candlestick)

        # Check if bull flag attributes are updated correctly
        self.assertEqual(opportunity.bull_flag_open_close, 10.0)
        self.assertEqual(opportunity.bull_flag_return_pct, 0.1)

    def test_set_consolidation(self):
        opportunity = BullFlagOpportunity(
            start=self.start_time, end=self.end_time
        )

        # Set bull flag to use in consolidation
        self.candlestick.close = 110
        self.candlestick.open = 100
        opportunity.set_bull_flag(self.candlestick)

        # Create a consolidation period with multiple candlesticks
        consolidation_period = [
            Candlestick(
                self.start_time + timedelta(minutes=i), duration_in_seconds=60
            )
            for i in range(1, 6)
        ]
        for i, candlestick in enumerate(consolidation_period, start=1):
            candlestick.open = 100 + i
            candlestick.low = 100 + i
            candlestick.close = 105 + i
            candlestick.high = 105 + i

        opportunity.set_consolidation(consolidation_period)

        # Check if consolidation attributes are updated correctly
        self.assertEqual(opportunity.consolidation_period_length, 5)
        self.assertEqual(opportunity.consolidation_period_max_ratio, 0.5)
        self.assertEqual(opportunity.expected_trade_price, 110)

    def test_set_consolidation_with_bull_flag_having_equal_open_close(self):
        opportunity = BullFlagOpportunity(
            start=self.start_time, end=self.end_time
        )

        # Set bull flag to use in consolidation
        self.candlestick.close = 100
        self.candlestick.open = 100
        opportunity.set_bull_flag(self.candlestick)

        # Create a consolidation period with multiple candlesticks
        consolidation_period = [
            Candlestick(
                self.start_time + timedelta(minutes=i), duration_in_seconds=60
            )
            for i in range(1, 6)
        ]
        for i, candlestick in enumerate(consolidation_period, start=1):
            candlestick.close = 105 + i
            candlestick.open = 100 + i

        opportunity.set_consolidation(consolidation_period)

        # Check if consolidation attributes are updated correctly
        self.assertEqual(opportunity.consolidation_period_length, 5)
        self.assertEqual(opportunity.consolidation_period_max_ratio, math.inf)
        self.assertEqual(opportunity.expected_trade_price, 110)

    def test_grade(self):
        opportunity = BullFlagOpportunity(
            start=self.start_time, end=self.end_time
        )

        # Set bull flag and consolidation to grade the opportunity
        self.candlestick.open = 100
        self.candlestick.low = 100
        self.candlestick.close = 110
        self.candlestick.high = 110
        opportunity.set_bull_flag(self.candlestick)

        consolidation_period = [
            Candlestick(
                self.start_time + timedelta(minutes=i), duration_in_seconds=60
            )
            for i in range(1, 6)
        ]
        for i, candlestick in enumerate(consolidation_period, start=1):
            candlestick.open = 100 + i
            candlestick.low = 100 + i
            candlestick.close = 103 + i
            candlestick.high = 103 + i

        opportunity.set_consolidation(consolidation_period)

        # Grade the opportunity and check the score
        opportunity.grade(self.params)
        self.assertAlmostEqual(opportunity.score, 0.5)
