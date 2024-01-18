import math
import unittest
from datetime import datetime, timedelta
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)
from jolteon.strategy.core.patterns.bull_flag.recognizer import (
    BullFlagRecognizer,
)


class TestRecognizer(unittest.TestCase):
    def setUp(self):
        self.params = BullFlagParameters(verbose=True)
        self.start_time = datetime(2024, 1, 1, 0, 0, 0)
        self.candlesticks = [
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=100,
                high=120,
                close=110,
                low=90,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=1),
                duration_in_seconds=60,
                open=100,
                high=120,
                close=200,
                low=90,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=2),
                duration_in_seconds=60,
                open=100,
                high=120,
                close=110,
                low=90,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=3),
                duration_in_seconds=60,
                open=100,
                high=120,
                close=110,
                low=90,
            ),
        ]
        self.pattern_recognizer = BullFlagRecognizer(self.params)

        self.patterns = list[BullFlagPattern]()
        self.pattern_recognizer.bull_flag_signal.connect(self.handle_signal)

    def handle_signal(self, _: str, pattern: BullFlagPattern):
        self.patterns.append(pattern)

    def test_bull_flag(self):
        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:3])
        self.assertEqual(1, len(self.patterns))
        self.assertEqual(RecognitionResult.BULL_FLAG, self.patterns[0].result)

    def test_consolidation_period(self):
        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:3])
        self.assertEqual(1, len(self.patterns))
        self.assertEqual(1, len(self.patterns[0].consolidation))
        self.assertEqual(0.1, self.patterns[0].consolidation_max_ratio)

        self.pattern_recognizer.on_candlestick("_", self.candlesticks[3])
        self.assertEqual(2, len(self.patterns[-1].consolidation))
        self.assertEqual(0.1, self.patterns[-1].consolidation_max_ratio)

    def test_no_consolidation_period(self):
        self.candlesticks[3].close = 1000
        self.pattern_recognizer.on_candlesticks("_", self.candlesticks)
        self.assertEqual(
            RecognitionResult.NO_CONSOLIDATION_PERIOD, self.patterns[-1].result
        )
        self.assertEqual(2, len(self.patterns[-1].consolidation))
        self.assertEqual(9.0, self.patterns[-1].consolidation_max_ratio)

    def test_not_enough_candlesticks(self):
        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:2])
        self.assertEqual(0, len(self.patterns))

        self.pattern_recognizer.on_candlestick("_", self.candlesticks[3])
        self.assertEqual(1, len(self.patterns))

    def test_not_extremely_bullish(self):
        # Change close price to make it not extremely bullish
        self.candlesticks[1].close = 120

        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:3])
        self.assertEqual(1, len(self.patterns))
        self.assertEqual(
            RecognitionResult.NO_EXTREME_BULLISH, self.patterns[0].result
        )

    def test_not_extremely_bullish_equal_open_close(self):
        # Change close price to make it not extremely bullish
        self.candlesticks[1].close = self.candlesticks[1].open

        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:3])
        self.assertLessEqual(1, len(self.patterns))
        self.assertEqual(1, len(self.patterns[-1].consolidation))
        self.assertEqual(math.inf, self.patterns[-1].consolidation_max_ratio)

    def test_not_extremely_bullish_equal_open_close_2(self):
        # Change close price to make it not extremely bullish
        self.candlesticks[1].close = self.candlesticks[1].open
        self.candlesticks[2].close = self.candlesticks[1].open

        self.pattern_recognizer.on_candlesticks("_", self.candlesticks[0:3])
        self.assertLessEqual(1, len(self.patterns))
        self.assertEqual(1, len(self.patterns[-1].consolidation))
        self.assertEqual(0, self.patterns[-1].consolidation_max_ratio)

    def test_multiple_candlesticks_not_in_time_order(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[-1])

        with self.assertRaises(AssertionError):
            self.pattern_recognizer.on_candlestick("_", self.candlesticks[-2])

    def test_multiple_candlesticks_merge(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[-1])
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[-1])
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[-1])
        self.assertLessEqual(0, len(self.patterns))
