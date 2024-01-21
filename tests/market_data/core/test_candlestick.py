import unittest
from datetime import datetime, timedelta

import pytz

from jolteon.market_data.core.candlestick import Candlestick


class TestCandlestick(unittest.IsolatedAsyncioTestCase):
    async def test_candlestick(self):
        now = datetime(
            year=2024,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        candle = Candlestick(now, 1)

        self.assertEqual(candle.open, 0.0)
        self.assertEqual(candle.high, 0.0)
        self.assertEqual(candle.low, 0.0)
        self.assertEqual(candle.close, 0.0)
        self.assertEqual(candle.volume, 0.0)
        self.assertEqual(
            str(candle),
            "Candlestick("
            "Open=0.0, "
            "High=0.0, "
            "Low=0.0, "
            "Close=0.0, "
            "Volume=0.0, "
            "StartTime=2024-01-01 00:00:00, "
            "EndTime=2024-01-01 00:00:01, "
            "ReturnPct=0.0, "
            "CashValueChange=0.0)",
        )

    async def test_candlestick_add_trade_failure(self):
        now = datetime.now(pytz.utc)
        candle = Candlestick(now, 1)
        self.assertFalse(
            candle.add_trade(
                trade_price=1.23,
                trade_quantity=2.34,
                transaction_time=now + timedelta(days=1),
            )
        )

    async def test_candlestick_is_completed(self):
        now = datetime.now(pytz.utc)

        candle = Candlestick(now, 1)
        self.assertFalse(candle.is_completed(now))

        self.assertTrue(
            candle.add_trade(
                trade_price=1.23, trade_quantity=2.34, transaction_time=now
            )
        )
        self.assertFalse(candle.is_completed(now - timedelta(seconds=1)))
        self.assertTrue(candle.is_completed(now + timedelta(seconds=1)))

    async def test_candlestick_is_bullish_bearish(self):
        now = datetime.now(pytz.utc)

        candle = Candlestick(now, 1)
        self.assertFalse(candle.is_bullish())
        self.assertFalse(candle.is_bearish())

        self.assertTrue(
            candle.add_trade(
                trade_price=1.0, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertFalse(candle.is_bullish())
        self.assertFalse(candle.is_bearish())

        self.assertTrue(
            candle.add_trade(
                trade_price=2.0, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertTrue(candle.is_bullish())
        self.assertFalse(candle.is_bearish())

        self.assertTrue(
            candle.add_trade(
                trade_price=0.9, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertFalse(candle.is_bullish())
        self.assertTrue(candle.is_bearish())

    async def test_candlestick_return_percentage(self):
        now = datetime.now(pytz.utc)

        candle = Candlestick(now, 1)

        self.assertTrue(
            candle.add_trade(
                trade_price=1.0, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertEqual(candle.return_percentage(), 0.0)

        self.assertTrue(
            candle.add_trade(
                trade_price=2.0, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertEqual(candle.return_percentage(), 1.0)

        self.assertTrue(
            candle.add_trade(
                trade_price=0.1, trade_quantity=2.0, transaction_time=now
            )
        )
        self.assertEqual(candle.return_percentage(), -0.9)

    async def test_candlestick_with_1_trade(self):
        now = datetime.now(pytz.utc)
        candle = Candlestick(now, 1)
        self.assertTrue(
            candle.add_trade(
                trade_price=1.23, trade_quantity=2.34, transaction_time=now
            )
        )

        self.assertEqual(candle.open, 1.23)
        self.assertEqual(candle.high, 1.23)
        self.assertEqual(candle.low, 1.23)
        self.assertEqual(candle.close, 1.23)
        self.assertEqual(candle.volume, 2.34)

    async def test_candlestick_with_multi_trade(self):
        now = datetime.now(pytz.utc)
        candle = Candlestick(now, 1)
        self.assertTrue(
            candle.add_trade(
                trade_price=1.23, trade_quantity=2.34, transaction_time=now
            )
        )
        self.assertTrue(
            candle.add_trade(
                trade_price=0.01, trade_quantity=1.00, transaction_time=now
            )
        )

        self.assertEqual(candle.open, 1.23)
        self.assertEqual(candle.high, 1.23)
        self.assertEqual(candle.low, 0.01)
        self.assertEqual(candle.close, 0.01)
        self.assertEqual(candle.volume, 3.34)

        candle.add_trade(
            trade_price=10.00, trade_quantity=1.00, transaction_time=now
        )
        self.assertEqual(candle.open, 1.23)
        self.assertEqual(candle.high, 10.00)
        self.assertEqual(candle.low, 0.01)
        self.assertEqual(candle.close, 10.00)
        self.assertEqual(candle.volume, 4.34)

    async def test_candlestick_is_hammer(self):
        now = datetime.now(pytz.utc)
        candle = Candlestick(now, 1, open=1.0, high=1.01, low=0.01, close=0.99)

        self.assertTrue(candle.is_hammer())
