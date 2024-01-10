import unittest
from datetime import datetime, timezone

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.common.candlestick_generator import (
    CandlestickGenerator,
)
from crypto_trading_engine.market_data.core.trade import Trade


class TestCandlestickGenerator(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def create_mock_trade(second: int = 0):
        return Trade(
            trade_id=0,
            sequence_number=0,
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=MarketSide.BUY,
            price=1.0,
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
        candlesticks = candlestick_generator.on_trade(self.create_mock_trade())

        self.assertEqual(len(candlesticks), 1)
        self.assertEqual(candlesticks[0].open, 1)
        self.assertEqual(candlesticks[0].high, 1)
        self.assertEqual(candlesticks[0].low, 1)
        self.assertEqual(candlesticks[0].close, 1)
        self.assertEqual(candlesticks[0].volume, 1)

    async def test_candlestick_generator_2_trades_in_same_time_window(self):
        candlestick_generator = CandlestickGenerator(1)
        candlestick_generator.on_trade(self.create_mock_trade())
        candlesticks = candlestick_generator.on_trade(self.create_mock_trade())

        self.assertEqual(len(candlesticks), 1)
        self.assertEqual(candlesticks[0].open, 1)
        self.assertEqual(candlesticks[0].high, 1)
        self.assertEqual(candlesticks[0].low, 1)
        self.assertEqual(candlesticks[0].close, 1)
        self.assertEqual(candlesticks[0].volume, 2)

    async def test_candlestick_generator_2_trades_in_different_time_window(
        self,
    ):
        candlestick_generator = CandlestickGenerator(1)
        candlestick_generator.on_trade(self.create_mock_trade())
        candlesticks = candlestick_generator.on_trade(
            self.create_mock_trade(second=10)
        )

        self.assertEqual(len(candlesticks), 2)

        self.assertEqual(candlesticks[0].open, 1)
        self.assertEqual(candlesticks[0].high, 1)
        self.assertEqual(candlesticks[0].low, 1)
        self.assertEqual(candlesticks[0].close, 1)
        self.assertEqual(candlesticks[0].volume, 1)

        self.assertEqual(candlesticks[1].open, 1)
        self.assertEqual(candlesticks[1].high, 1)
        self.assertEqual(candlesticks[1].low, 1)
        self.assertEqual(candlesticks[1].close, 1)
        self.assertEqual(candlesticks[1].volume, 1)
