import unittest
from unittest.mock import patch, AsyncMock, Mock

from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbasePublicFeed,
    CoinbaseEnvironment,
)


class TestCandlestick(unittest.IsolatedAsyncioTestCase):
    heartbeat_feed = """
    {
        "type":"heartbeat"
    }
    """
    ticker_feed = """
    {
       "type":"ticker"
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

    @patch("websockets.connect")
    async def test_connect_to_production_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.error
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        await CoinbasePublicFeed(CoinbaseEnvironment.PRODUCTION).connect(
            ["ETH-USD"]
        )

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_connect_to_sandbox_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.error
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        await CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX).connect(
            ["ETH-USD"]
        )

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed-public.sandbox.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_heartbeat_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.heartbeat_feed,
            TestCandlestick.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        feed = CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX)
        feed.events = Mock()
        await feed.connect(["ETH-USD"])

        # Assertions
        self.assertEqual(
            mock_websocket.__aenter__.return_value.recv.call_count, 2
        )
        self.assertEqual(
            feed.events.
        )

    @patch("websockets.connect")
    async def test_subscriptions_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.subscriptions_feed,
            TestCandlestick.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        await CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX).connect(
            ["ETH-USD"]
        )

        # Assertions
        self.assertEqual(
            mock_websocket.__aenter__.return_value.recv.call_count, 2
        )

    @patch("websockets.connect")
    async def test_ticker_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.ticker_feed,
            TestCandlestick.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        await CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX).connect(
            ["ETH-USD"]
        )

        # Assertions
        self.assertEqual(
            mock_websocket.__aenter__.return_value.recv.call_count, 2
        )

    @patch("websockets.connect")
    async def test_match_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = [
            TestCandlestick.match_feed,
            TestCandlestick.error,
        ]

        # Set up the mock context manager
        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()

        await CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX).connect(
            ["ETH-USD"]
        )

        # Assertions
        self.assertEqual(
            mock_websocket.__aenter__.return_value.recv.call_count, 2
        )
