import unittest
from datetime import datetime, timedelta
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)


class TestBullFlagPattern(unittest.TestCase):
    def setUp(self):
        # Create example candlesticks for testing
        self.start_time = datetime(2022, 1, 1, 0, 0, 0)
        bull_flag_candlestick = Candlestick(
            self.start_time, 60, open=100, close=110
        )
        consolidation_candlesticks = [
            Candlestick(
                self.start_time + timedelta(hours=i),
                3600,
                open=105,
                close=106,
            )
            for i in range(3)
        ]
        self.bull_flag_pattern = BullFlagPattern(
            bull_flag_candlestick, consolidation_candlesticks
        )

    def test_pattern_creation(self):
        self.assertIsInstance(self.bull_flag_pattern, BullFlagPattern)
        self.assertEqual(self.bull_flag_pattern.bull_flag_body, 10)

    def test_start_end_time(self):
        self.assertEqual(self.bull_flag_pattern.start, self.start_time)
        self.assertEqual(
            self.bull_flag_pattern.end, self.start_time + timedelta(hours=3)
        )

    def test_consolidation_max_ratio(self):
        self.assertAlmostEqual(
            self.bull_flag_pattern.consolidation_max_ratio, 0.1
        )

    def test_initial_recognition_result(self):
        self.assertEqual(
            self.bull_flag_pattern.result, RecognitionResult.UNKNOWN
        )
