import json
import unittest
from unittest.mock import Mock, AsyncMock

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

    async def test_connect(self):
        symbol = "BTC/USD"
        # Create an instance of PublicFeed
        public_feed = PublicFeed()
        public_feed.client = AsyncMock()
        public_feed.exception_occurred = True
        # noinspection PyTypeChecker
        await public_feed.connect(symbol)

        # Assert that the subscribe method was called with the correct
        # parameters
        public_feed.client.subscribe.assert_called_with(
            params={"channel": "trade", "symbol": [symbol]}
        )

    async def test_heartbeat_feed(self):
        feed = PublicFeed()
        feed.events = Mock()
        await feed._on_message(json.loads(TestPublicFeed.heartbeat_feed))

        # Assertions
        self.assertEqual(1, feed.events.channel_heartbeat.send.call_count)

    async def test_trade_feed(self):
        feed = PublicFeed()
        feed.events = Mock()
        await feed._on_message(json.loads(TestPublicFeed.trade_feed))

        self.assertEqual(3, feed.events.candlestick.send.call_count)

    async def test_unknown_feed(self):
        feed = PublicFeed()
        feed.events = Mock()
        await feed._on_message(json.loads(TestPublicFeed.unknown_feed))

        # Assertions
        self.assertEqual(0, feed.events.channel_heartbeat.send.call_count)
        self.assertEqual(0, feed.events.candlestick.send.call_count)
