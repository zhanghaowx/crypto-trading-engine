import unittest
from datetime import datetime

from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
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
        self.params = StrategyParameters()
