import json
import unittest
from unittest.mock import Mock, AsyncMock, patch

from jolteon.core.health_monitor.heartbeat import HeartbeatLevel
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

    @patch("asyncio.sleep", return_value=None)
    async def test_connect(self, mock_sleep):
        symbol = "BTC/USD"
        # Create an instance of PublicFeed
        self.feed._client = AsyncMock()
        # Avoid entering an infinite loop
        self.feed._exception_occurred = True
        # noinspection PyTypeChecker
        await self.feed.async_connect(symbol)

        # Assert that the subscribe method was called with the correct
        # parameters
        self.feed._client.subscribe.assert_called_with(
            params={"channel": "trade", "symbol": [symbol]}
        )

    async def test_on_message_success(self):
        self.assertFalse(self.feed._exception_occurred)
        await self.feed.on_message(json.loads(TestPublicFeed.pong_feed))
        self.assertFalse(self.feed._exception_occurred)

    async def test_on_message_fail(self):
        self.assertFalse(self.feed._exception_occurred)
        await self.feed.on_message([])
        self.assertTrue(self.feed._exception_occurred)

    async def test_pong_feed(self):
        await self.feed.on_message(json.loads(TestPublicFeed.pong_feed))

        # Nothing happened
        self.assertEqual(0, self.feed.events.channel_heartbeat.send.call_count)
        self.assertEqual(0, self.feed.events.matches.send.call_count)
        self.assertEqual(0, self.feed.events.candlestick.send.call_count)

    async def test_heartbeat_feed(self):
        await self.feed.on_message(json.loads(TestPublicFeed.heartbeat_feed))

        # Assertions
        self.assertEqual(1, self.feed.events.channel_heartbeat.send.call_count)

    async def test_trade_feed(self):
        await self.feed.on_message(json.loads(TestPublicFeed.trade_feed))

        self.assertEqual(3, self.feed.events.candlestick.send.call_count)

    async def test_unknown_feed(self):
        await self.feed.on_message(json.loads(TestPublicFeed.unknown_feed))

        # Nothing happened
        self.assertEqual(0, self.feed.events.channel_heartbeat.send.call_count)
        self.assertEqual(0, self.feed.events.matches.send.call_count)
        self.assertEqual(0, self.feed.events.candlestick.send.call_count)

    async def test_error_feed(self):
        await self.feed.on_message(json.loads(TestPublicFeed.error_feed))
        self.assertEqual(HeartbeatLevel.ERROR, self.feed._issues[-1].level)

        await self.feed.on_message(json.loads(TestPublicFeed.subscribe_feed))
        self.assertEqual(HeartbeatLevel.NORMAL, self.feed._issues[-1].level)
