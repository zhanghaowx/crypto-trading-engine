import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.coinbase.historical_feed import (
    HistoricalFeed,
)
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.events import Events


class TestHistoricalFeed(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.historical_feed = HistoricalFeed(
            api_key="api_key", api_secret="api_secret"
        )
        self.historical_feed._client = Mock()
        self.historical_feed._client.get_market_trades.return_value = {
            "trades": [
                {
                    "trade_id": "34b080bf-fcfd-445a-832b-46b5ddc65601",
                    "product_id": "BTC-USD",
                    "price": "140.91",
                    "size": "4",
                    "time": "2021-05-31T09:59:59Z",
                    "side": "BUY",
                    "bid": "291.13",
                    "ask": "292.40",
                }
            ],
            "best_bid": "291.13",
            "best_ask": "292.40",
        }
        self.historical_feed.events.candlestick.connect(self.on_candlestick)
        self.candlesticks = list[Candlestick]()

    async def asyncTearDown(self):
        time_manager().force_reset()

    def on_candlestick(self, _, candlestick):
        self.candlesticks.append(candlestick)

    async def test_connect_with_valid_symbol(self):
        symbol = "BTC-USD"
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )

        # Validate raised candlestick event
        self.assertEqual(1, len(self.candlesticks))
        self.assertEqual(140.91, self.candlesticks[0].open)
        self.assertEqual(140.91, self.candlesticks[0].high)
        self.assertEqual(140.91, self.candlesticks[0].low)
        self.assertEqual(140.91, self.candlesticks[0].close)
        self.assertEqual(4.0, self.candlesticks[0].volume)

    async def test_connect_with_valid_symbol_and_cache(self):
        HistoricalFeed.CACHE.clear()

        symbol = "BTC-USD"
        now = time_manager().now()
        await self.historical_feed.connect(
            symbol, now - timedelta(minutes=1), now
        )
        await self.historical_feed.connect(
            symbol, now - timedelta(minutes=1), now
        )

        self.assertEqual(1, len(HistoricalFeed.CACHE))
        self.assertEqual(2, len(self.candlesticks))
        self.assertEqual(self.candlesticks[0], self.candlesticks[1])

        self.historical_feed._client.get_market_trades.assert_called_once()

    @patch("asyncio.sleep", return_value=None)
    @patch.object(Events.candlestick, "send")
    async def test_connect_with_replay_speed(self, mock_send, mock_sleep):
        symbol = "BTC-USD"

        self.historical_feed._replay_speed = 1
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )
        mock_sleep.assert_called_once_with(60)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 2
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )
        mock_sleep.assert_called_once_with(30)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 3
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )
        mock_sleep.assert_called_once_with(20)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 30
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )
        mock_sleep.assert_called_once_with(2)
        mock_sleep.reset_mock()

        self.historical_feed._replay_speed = 60
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(minutes=1),
            time_manager().now(),
        )
        mock_sleep.assert_called_once_with(1)
        mock_sleep.reset_mock()
