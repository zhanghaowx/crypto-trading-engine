import unittest
from datetime import datetime, timezone

from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick_generator import (
    CandlestickGenerator,
)
from jolteon.market_data.core.trade import Trade


class TestCandlestickGenerator(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def create_mock_trade(price: float = 1.0, second: int = 0):
        return Trade(
            trade_id=0,
            client_order_id="",
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=MarketSide.BUY,
            price=price,
            quantity=1.0,
            transaction_time=datetime(
                year=2024,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=second,
                microsecond=0,
                tzinfo=timezone.utc,
            ),
        )

    async def test_candlestick_generator_1_trade(self):
        candlestick_generator = CandlestickGenerator(1)
        candlesticks = candlestick_generator.on_market_trade(
            self.create_mock_trade()
        )

        self.assertEqual(len(candlesticks), 1)
        self.assertEqual(candlesticks[0].open, 1)
        self.assertEqual(candlesticks[0].high, 1)
        self.assertEqual(candlesticks[0].low, 1)
        self.assertEqual(candlesticks[0].close, 1)
        self.assertEqual(candlesticks[0].volume, 1)

    async def test_candlestick_generator_2_trades_in_same_time_window(self):
        candlestick_generator = CandlestickGenerator(interval_in_seconds=1)
        candlesticks = candlestick_generator.on_market_trade(
            self.create_mock_trade(price=2.0, second=0)
        )
        self.assertEqual(len(candlesticks), 1)

        self.assertEqual(candlesticks[0].open, 2)
        self.assertEqual(candlesticks[0].high, 2)
        self.assertEqual(candlesticks[0].low, 2)
        self.assertEqual(candlesticks[0].close, 2)
        self.assertEqual(candlesticks[0].volume, 1)

        candlesticks = candlestick_generator.on_market_trade(
            self.create_mock_trade(price=3.0, second=0)
        )
        self.assertEqual(candlesticks[0].open, 2)
        self.assertEqual(candlesticks[0].high, 3)
        self.assertEqual(candlesticks[0].low, 2)
        self.assertEqual(candlesticks[0].close, 3)
        self.assertEqual(candlesticks[0].volume, 2)
    async def test_candlestick_generator_2_trades_in_different_time_window(
        self,
    ):
        candlestick_generator = CandlestickGenerator(interval_in_seconds=1)
        candlesticks = candlestick_generator.on_market_trade(
            self.create_mock_trade(price=2.0, second=0)
        )
        self.assertEqual(len(candlesticks), 1)

        self.assertEqual(candlesticks[0].open, 2)
        self.assertEqual(candlesticks[0].high, 2)
        self.assertEqual(candlesticks[0].low, 2)
        self.assertEqual(candlesticks[0].close, 2)
        self.assertEqual(candlesticks[0].volume, 1)

        candlesticks = candlestick_generator.on_market_trade(
            self.create_mock_trade(price=3.0, second=10)
        )
        self.assertEqual(candlesticks[0].open, 3)
        self.assertEqual(candlesticks[0].high, 3)
        self.assertEqual(candlesticks[0].low, 3)
        self.assertEqual(candlesticks[0].close, 3)
        self.assertEqual(candlesticks[0].volume, 1)
