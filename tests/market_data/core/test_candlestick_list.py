import unittest
from datetime import datetime, timedelta
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.candlestick_list import (
    CandlestickList,
)


class TestCandlestickList(unittest.TestCase):
    def test_add_candlestick_empty_list(self):
        candlestick_list = CandlestickList(max_length=5)
        candlestick = Candlestick(
            start=datetime(2022, 1, 1),
            duration_in_seconds=60,
            open=100,
            close=110,
        )
        candlestick_list.add_candlestick(candlestick)
        self.assertEqual(len(candlestick_list.candlesticks), 1)
        self.assertEqual(candlestick_list.candlesticks[0], candlestick)

    def test_add_candlestick_in_order(self):
        candlestick_list = CandlestickList(max_length=5)
        candlestick1 = Candlestick(
            start=datetime(2022, 1, 1),
            duration_in_seconds=60,
            open=100,
            close=110,
        )
        candlestick2 = Candlestick(
            start=datetime(2022, 1, 2),
            duration_in_seconds=60,
            open=110,
            close=120,
        )
        candlestick_list.add_candlestick(candlestick1)
        candlestick_list.add_candlestick(candlestick2)
        self.assertEqual(len(candlestick_list.candlesticks), 2)
        self.assertEqual(
            list(candlestick_list.candlesticks), [candlestick1, candlestick2]
        )

    def test_add_candlestick_out_of_order(self):
        candlestick_list = CandlestickList(max_length=5)
        candlestick1 = Candlestick(
            start=datetime(2022, 1, 2),
            duration_in_seconds=60,
            open=110,
            close=120,
        )
        candlestick2 = Candlestick(
            start=datetime(2022, 1, 1),
            duration_in_seconds=60,
            open=100,
            close=110,
        )
        candlestick_list.add_candlestick(candlestick1)

        with self.assertRaises(AssertionError) as context:
            candlestick_list.add_candlestick(candlestick2)
        self.assertRegex(
            str(context.exception),
            "^Candlesticks shall be sent in time order!",
        )

    def test_add_candlestick_replace_existing(self):
        candlestick_list = CandlestickList(max_length=5)
        candlestick1 = Candlestick(
            start=datetime(2022, 1, 1),
            duration_in_seconds=60,
            open=100,
            close=110,
        )
        candlestick2 = Candlestick(
            start=datetime(2022, 1, 1),
            duration_in_seconds=60,
            open=105,
            close=115,
        )
        candlestick_list.add_candlestick(candlestick1)
        candlestick_list.add_candlestick(candlestick2)
        self.assertEqual(len(candlestick_list.candlesticks), 1)
        self.assertEqual(candlestick_list.candlesticks[0], candlestick2)

    def test_atr(self):
        candlestick_list = CandlestickList(max_length=5)
        # Add candlesticks with different price movements for ATR calculation
        for i in range(1, 6):
            start = datetime(2022, 1, i)
            candlestick = Candlestick(
                start=start,
                duration_in_seconds=60,
                open=100 + i,
                high=110 + i,
                close=105 + i,
                low=100 + i,
            )
            candlestick_list.add_candlestick(candlestick)

        # Calculate ATR for the last 3 candlesticks
        atr_result = candlestick_list.atr(period=3)

        self.assertTrue(isinstance(atr_result, float))
        self.assertAlmostEqual(atr_result, 6.6666666666666667)
