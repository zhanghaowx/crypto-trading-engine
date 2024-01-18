import unittest
from datetime import datetime, timedelta

from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)
from jolteon.strategy.core.patterns.shooting_star.pattern import (
    ShootingStarPattern,
)
from jolteon.strategy.core.patterns.shooting_star.recognizer import (
    ShootingStarRecognizer,
)


class TestRecognizer(unittest.TestCase):
    def setUp(self):
        self.params = ShootingStarParameters()
        self.start_time = datetime(2024, 1, 1, 0, 0, 0)
        self.candlesticks = [
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=1.0,
                low=0.99,
                close=1.01,
                high=10.0,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=1.0,
                low=0.99,
                close=1.00,
                high=10.0,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=1.0,
                low=0.99,
                close=1.00,
                high=1.01,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=1.0,
                low=1.0,
                close=1.0,
                high=1.0,
            ),
        ]
        self.pattern_recognizer = ShootingStarRecognizer(self.params)

        self.patterns = list[ShootingStarPattern]()
        self.pattern_recognizer.shooting_star_signal.connect(
            self.handle_signal
        )

    def handle_signal(self, _: str, pattern: ShootingStarPattern):
        self.patterns.append(pattern)

    def test_shooting_star(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[0])
        self.assertEqual(1, len(self.patterns))

    def test_shooting_star_equal_high_low(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[3])
        self.assertEqual(0, len(self.patterns))

    def test_shooting_star_equal_open_close(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[2])
        self.assertEqual(0, len(self.patterns))

    def test_shooting_star_equal_open_close_small_upper_shadows(self):
        self.pattern_recognizer.on_candlestick("_", self.candlesticks[1])
        self.assertEqual(1, len(self.patterns))
