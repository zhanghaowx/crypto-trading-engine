import unittest
from unittest.mock import Mock, AsyncMock, patch

import websockets

from jolteon.market_data.kraken.public_feed import PublicFeed


class TestPublicFeed(unittest.IsolatedAsyncioTestCase):
    unknown_feed = """
    {
        "type":"unknown"
    }
    """
    error_feed = """
    {
        "error":"get an error message"
    }
    """
    heartbeat_feed = """
    {
        "channel":"heartbeat"
    }
    """
    pong_feed = """
    {
        "method":"pong"
    }
    """
    subscribe_feed = """
    {
        "method":"subscribe"
    }
    """
    trade_feed = """
    {
      "channel": "trade",
      "data": [
        {
          "ord_type": "market",
          "price": 4136.4,
          "qty": 0.23374249,
          "side": "sell",
          "symbol": "BTC/USD",
          "timestamp": "2022-06-13T08:09:10.123456Z",
          "trade_id": 0
        },
        {
          "ord_type": "market",
          "price": 4136.4,
          "qty": 0.00060615,
          "side": "sell",
          "symbol": "BTC/USD",
          "timestamp": "2022-06-13T08:09:20.123456Z",
          "trade_id": 0
        },
        {
          "ord_type": "market",
          "price": 4136.4,
          "qty": 0.00000136,
          "side": "sell",
          "symbol": "BTC/USD",
          "timestamp": "2022-06-13T08:09:30.123456Z",
          "trade_id": 0
        }
      ],
      "type": "update"
    }
    """

    async def asyncSetUp(self):
        self.feed = PublicFeed()
        self.feed.events = Mock()

    @staticmethod
    async def create_mock_websocket(
        mock_connect: object, feeds: list[object]
    ) -> AsyncMock:
        # Create a mock websocket object
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__.return_value.recv.side_effect = feeds

        async def async_context_manager(*args, **kwargs):
            return mock_websocket

        mock_connect.return_value = await async_context_manager()
        return mock_websocket

    @patch("websockets.connect")
    async def test_connect_to_production_feed(self, mock_connect):
        await self.create_mock_websocket(mock_connect, [])

        await self.feed.connect("ETH-USD")

        # Assertions
        mock_connect.assert_called_once_with("wss://ws.kraken.com/v2")

    @patch("websockets.connect")
    async def test_heartbeat_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.heartbeat_feed]
        )

        await self.feed.connect("ETH-USD")

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(1, self.feed.events.channel_heartbeat.send.call_count)

    @patch("websockets.connect")
    async def test_subscriptions_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.subscribe_feed]
        )

        await self.feed.connect("ETH-USD")

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_pong_feed(self, mock_connect):
        # Create a mock websocket object
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.pong_feed]
        )

        await self.feed.connect("ETH-USD")

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_match_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.trade_feed]
        )

        await self.feed.connect("ETH-USD")

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(3, self.feed.events.candlestick.send.call_count)

    @patch("websockets.connect")
    async def test_unknown_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.unknown_feed]
        )

        await self.feed.connect("ETH-USD")

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

        await self.feed.connect("ETH-USD")

        # Assertions
        self.assertEqual(
            1, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_exception_with_retries(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect,
            [
                websockets.exceptions.ConnectionClosedError(
                    rcvd=None, sent=None
                ),
            ],
        )

        await self.feed.connect(
            "ETH-USD", max_retries=2, retry_interval_in_seconds=0.001
        )

        # Assertions
        self.assertEqual(
            3, mock_websocket.__aenter__.return_value.recv.call_count
        )
