import unittest
from datetime import datetime

from jolteon.core.event.signal import subscribe
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.indicator.rsi import RSICalculator, RSI


class TestRSICalculator(unittest.TestCase):
    def setUp(self):
        self.received_rsi = list[RSI]()

    @subscribe("rsi")
    def on_rsi(self, _: str, rsi: RSI):
        self.received_rsi.append(rsi)

    def test_rsi_calculation(self):
        # Create RSICalculator instance
        rsi_calculator = RSICalculator(period=2)
        rsi_calculator.rsi_event.connect(self.on_rsi)

        # Simulate receiving candlestick data
        candlesticks = [
            Candlestick(
                start=datetime(2024, 1, 1, 0, 0),
                duration_in_seconds=60,
                open=100,
                high=105,
                low=95,
                close=100,
                volume=1000,
            ),
            Candlestick(
                start=datetime(2024, 1, 1, 0, 1),
                duration_in_seconds=60,
                open=102,
                high=108,
                low=100,
                close=105,
                volume=1200,
            ),
            Candlestick(
                start=datetime(2024, 1, 1, 0, 2),
                duration_in_seconds=60,
                open=102,
                high=108,
                low=100,
                close=105,
                volume=1200,
            ),
            Candlestick(
                start=datetime(2024, 1, 1, 0, 3),
                duration_in_seconds=60,
                open=102,
                high=108,
                low=100,
                close=105,
                volume=1200,
            ),
            Candlestick(
                start=datetime(2024, 1, 1, 0, 4),
                duration_in_seconds=60,
                open=102,
                high=108,
                low=100,
                close=105,
                volume=1200,
            ),
        ]

        for candlestick in candlesticks:
            rsi_calculator.on_candlestick("", candlestick)

        # Test if RSI is calculated correctly
        self.assertEqual(2, len(self.received_rsi))
        self.assertAlmostEqual(100.0, self.received_rsi[0].rsi)
        self.assertAlmostEqual(100.0, self.received_rsi[1].rsi)

    def test_rsi_will_not_calculate_on_same_candlestick_update(self):
        rsi_calculator = RSICalculator(period=2)
        rsi_calculator.rsi_event.connect(self.on_rsi)

        # Simulate receiving candlestick data
        candlestick = Candlestick(
            start=datetime(2024, 1, 1, 0, 0),
            duration_in_seconds=60,
            open=100,
            high=105,
            low=95,
            close=100,
            volume=1000,
        )

        for i in range(0, 10):
            rsi_calculator.on_candlestick("", candlestick)

        self.assertEqual(0, len(self.received_rsi))
