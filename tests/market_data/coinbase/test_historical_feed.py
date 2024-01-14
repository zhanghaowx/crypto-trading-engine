import asyncio
import unittest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta

from crypto_trading_engine.core.time.time_manager import create_time_manager
from crypto_trading_engine.market_data.coinbase.historical_feed import (
    HistoricalFeed,
)
from crypto_trading_engine.market_data.core.candlestick import Candlestick


class TestHistoricalFeed(unittest.TestCase):
    def setUp(self):
        self.historical_feed = HistoricalFeed(
            api_key="api_key", api_secret="api_secret"
        )
        self.historical_feed._client = Mock()
        self.historical_feed._client.get_candles.return_value = {
            "candles": [
                {
                    "start": 1642819200,
                    "open": "100.0",
                    "high": "120.0",
                    "low": "80.0",
                    "close": "110.0",
                    "volume": "500.0",
                },
                # Add more candlestick data as needed
            ]
        }
        self.historical_feed.events.candlestick.connect(self.on_candlestick)
        self.candlesticks = list[Candlestick]()

    def tearDown(self):
        time_manager = create_time_manager()
        time_manager.force_reset()

    def on_candlestick(self, _, candlestick):
        self.candlesticks.append(candlestick)

    @patch("asyncio.sleep", return_value=None)
    def test_connect_with_valid_symbol(self, mock_sleep):
        symbol = "BTC-USD"
        asyncio.run(self.historical_feed.connect(symbol))

        # Validate raised candlestick event
        self.assertEqual(1, len(self.candlesticks))
        self.assertEqual(100.0, self.candlesticks[0].open)
        self.assertEqual(120.0, self.candlesticks[0].high)
        self.assertEqual(80.0, self.candlesticks[0].low)
        self.assertEqual(110.0, self.candlesticks[0].close)
        self.assertEqual(500.0, self.candlesticks[0].volume)

        mock_sleep.assert_called_once()

    @patch("asyncio.sleep", return_value=None)
    def test_connect_with_valid_symbol_and_cache(self, mock_sleep):
        HistoricalFeed.CACHE.clear()

        symbol = "BTC-USD"
        asyncio.run(self.historical_feed.connect(symbol))
        asyncio.run(self.historical_feed.connect(symbol))

        self.assertEqual(1, len(HistoricalFeed.CACHE))
        self.assertEqual(2, len(self.candlesticks))
        self.assertEqual(self.candlesticks[0], self.candlesticks[1])

        self.historical_feed._client.get_candles.assert_called_once()

    @patch("asyncio.sleep", return_value=None)
    @patch.object(HistoricalFeed.Events.candlestick, "send")
    def test_connect_with_replay_speed(self, mock_send, mock_sleep):
        symbol = "BTC-USD"

        self.historical_feed._replay_speed = 1
        self._candlestick_granularity = 60
        asyncio.run(self.historical_feed.connect(symbol))
        mock_sleep.assert_called_once_with(60)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 2
        self._candlestick_granularity = 60
        asyncio.run(self.historical_feed.connect(symbol))
        mock_sleep.assert_called_once_with(30)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 3
        self._candlestick_granularity = 60
        asyncio.run(self.historical_feed.connect(symbol))
        mock_sleep.assert_called_once_with(20)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 30
        self._candlestick_granularity = 60
        asyncio.run(self.historical_feed.connect(symbol))
        mock_sleep.assert_called_once_with(2)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 60
        self._candlestick_granularity = 60
        asyncio.run(self.historical_feed.connect(symbol))
        mock_sleep.assert_called_once_with(1)
        mock_sleep.reset_mock()
