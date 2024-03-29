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

    @staticmethod
    async def start_md_task(symbol: str, env: CoinbaseEnvironment):
        md = PublicFeed(env)
        md.events = MagicMock()
        await md.connect(symbol)
        return md

    @staticmethod
    async def create_mock_websocket(
        mock_connect: object, feeds: list[object]
    ) -> AsyncMock:
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = feeds + [
            TestPublicFeed.error
        ]

        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()
        return mock_websocket

    @patch("websockets.connect")
    async def test_connect_to_production_feed(self, mock_connect):
        await self.create_mock_websocket(mock_connect, [])
        await self.start_md_task("ETH-USD", CoinbaseEnvironment.PRODUCTION)

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_connect_to_sandbox_feed(self, mock_connect):
        await self.create_mock_websocket(mock_connect, [])
        await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        mock_connect.assert_called_once_with(
            "wss://ws-feed-public.sandbox.exchange.coinbase.com"
        )

    @patch("websockets.connect")
    async def test_heartbeat_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.heartbeat_feed]
        )
        feed = await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.channel_heartbeat.send.call_count)

    @patch("websockets.connect")
    async def test_subscriptions_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.subscriptions_feed]
        )
        await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_ticker_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.ticker_feed]
        )
        feed = await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.ticker.send.call_count)

    @patch("websockets.connect")
    async def test_match_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.match_feed]
        )
        feed = await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, feed.events.candlestick.send.call_count)

    @patch("websockets.connect")
    async def test_unknown_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.unknown_feed]
        )
        await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_exception(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect,
            [
                websockets.exceptions.ConnectionClosedError(
                    rcvd=None, sent=None
                ),
            ],
        )
        await self.start_md_task("ETH-USD", CoinbaseEnvironment.SANDBOX)

        # Assertions
        self.assertEqual(
            1, mock_websocket.__aenter__.return_value.recv.call_count
        )
