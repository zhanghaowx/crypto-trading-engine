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
