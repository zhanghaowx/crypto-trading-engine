import threading
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

import websockets

from jolteon.market_data.coinbase.public_feed import (
    PublicFeed,
    CoinbaseEnvironment,
)


class TestPublicFeed(unittest.IsolatedAsyncioTestCase):
    unknown_feed = """
    {
        "type":"unknown"
    }
    """
    heartbeat_feed = """
    {
        "type":"heartbeat"
    }
    """
    ticker_feed = """
    {
        "type": "ticker",
        "sequence": 37475248783,
        "product_id": "ETH-USD",
        "price": "1285.22",
        "open_24h": "1310.79",
        "volume_24h": "245532.79269678",
        "low_24h": "1280.52",
        "high_24h": "1313.8",
        "volume_30d": "9788783.60117027",
        "best_bid": "1285.04",
        "best_bid_size": "0.46688654",
        "best_ask": "1285.27",
        "best_ask_size": "1.56637040",
        "side": "buy",
        "time": "2022-10-19T23:28:22.061769Z",
        "trade_id": 370843401,
        "last_size": "11.4396987"
    }
    """
    match_feed = """
    {
        "type":"match",
        "trade_id":488446358,
        "maker_order_id":"432663f7-d90a-40c6-bdaa-2d8e33f7e378",
        "taker_order_id":"6d7362a5-baea-46ec-9faf-6a4446aee169",
        "side":"buy",
        "size":"0.00219265",
        "price":"2274.61",
        "product_id":"ETH-USD",
        "sequence":52808418658,
        "time":"2024-01-09T18:27:11.361885Z"
    }
    """
    subscriptions_feed = """
    {
        "type":"subscriptions"
    }
    """
    error = """
    {
        "type":"error", 
        "reason": "terminate"
    }
    """

    def start_md_thread(self, symbol: str, env: CoinbaseEnvironment, *args):
        md = PublicFeed(env)
        md.events = MagicMock()
        md_thread = threading.Thread(
            target=md.connect,
            args=(symbol, *args),
        )
        md_thread.start()
        md_thread.join()
        return md

    @patch("websockets.connect")
    async def test_connect_to_production_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.error
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        self.start_md_thread("ETH-USD", CoinbaseEnvironment.PRODUCTION)

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_connect_to_sandbox_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.error
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed-public.sandbox.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_heartbeat_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.heartbeat_feed,
            TestPublicFeed.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.channel_heartbeat.send.call_count)

    @patch("websockets.connect")
    async def test_subscriptions_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.subscriptions_feed,
            TestPublicFeed.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_ticker_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.ticker_feed,
            TestPublicFeed.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.ticker.send.call_count)

    @patch("websockets.connect")
    async def test_match_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.match_feed,
            TestPublicFeed.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.candlestick.send.call_count)

    @patch("websockets.connect")
    async def test_unknown_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestPublicFeed.unknown_feed,
            TestPublicFeed.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_exception(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            websockets.exceptions.ConnectionClosedError(rcvd=None, sent=None),
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = self.start_md_thread("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            1, mock_websocket.__aenter__.return_value.recv.call_count
        )
