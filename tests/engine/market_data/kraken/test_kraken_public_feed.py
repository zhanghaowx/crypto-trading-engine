import json
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import websockets

from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
    use_parameter_service,
)
from jolteon.engine.market_data.core.order_book import PriceLevel
from jolteon.engine.market_data.feed import IMarketDataFeed
from jolteon.engine.market_data.kraken.parameters import KrakenFeedParameters
from jolteon.engine.market_data.kraken.public_feed import PublicFeed


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
    trade_feed_1 = """
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
          "trade_id": 1
        },
        {
          "ord_type": "market",
          "price": 4136.4,
          "qty": 0.00060615,
          "side": "sell",
          "symbol": "BTC/USD",
          "timestamp": "2022-06-13T08:09:20.123456Z",
          "trade_id": 2
        },
        {
          "ord_type": "market",
          "price": 4136.4,
          "qty": 0.00000136,
          "side": "sell",
          "symbol": "BTC/USD",
          "timestamp": "2022-06-13T08:09:30.123456Z",
          "trade_id": 3
        }
      ],
      "type": "update"
    }
    """
    # Same as trade_feed_1 except all timestamps are +10 minute
    trade_feed_2 = """
        {
          "channel": "trade",
          "data": [
            {
              "ord_type": "market",
              "price": 4136.4,
              "qty": 0.23374249,
              "side": "sell",
              "symbol": "BTC/USD",
              "timestamp": "2022-06-13T08:19:10.123456Z",
              "trade_id": 4
            },
            {
              "ord_type": "market",
              "price": 4136.4,
              "qty": 0.00060615,
              "side": "sell",
              "symbol": "BTC/USD",
              "timestamp": "2022-06-13T08:19:20.123456Z",
              "trade_id": 5
            },
            {
              "ord_type": "market",
              "price": 4136.4,
              "qty": 0.00000136,
              "side": "sell",
              "symbol": "BTC/USD",
              "timestamp": "2022-06-13T08:19:30.123456Z",
              "trade_id": 6
            }
          ],
          "type": "update"
        }
        """
    ticker_feed_1 = """
    {
      "channel": "ticker",
      "data": [
        {
          "ask": 7000.3,
          "ask_qty": 0.01,
          "bid": 6000.0,
          "bid_qty": 0.01,
          "change": -100.0,
          "change_pct": -1.54,
          "high": 6500.9,
          "last": 6400.6,
          "low": 6400.1,
          "symbol": "BTC/EUR",
          "volume": 0.02,
          "vwap": 6450.2
        }
      ],
      "type": "snapshot"
    }
    """
    ticker_feed_2 = """
    {
      "channel": "ticker",
      "data": [
        {
          "ask": 7000.3,
          "ask_qty": 0.01,
          "bid": 6000.0,
          "bid_qty": 0.01,
          "change": -100.0,
          "change_pct": -1.54,
          "high": 6500.9,
          "last": 6400.6,
          "low": 6400.1,
          "symbol": "BTC/EUR",
          "volume": 0.02,
          "vwap": 6450.2
        }
      ],
      "type": "update"
    }
    """

    ticker_feed_3 = """
    {
      "channel": "ticker",
      "data": [
        {
          "ask": 7000.3,
          "ask_qty": 0.01,
          "bid": 6001.0,
          "bid_qty": 0.01,
          "change": -100.0,
          "change_pct": -1.54,
          "high": 6500.9,
          "last": 6400.6,
          "low": 6400.1,
          "symbol": "BTC/EUR",
          "volume": 0.02,
          "vwap": 6450.2
        }
      ],
      "type": "update"
    }
    """
    book_snapshot = """
    {
      "channel": "book",
      "data": [
        {
          "symbol": "BTC/USD",
          "bids": [
            {"price": 45283.5, "qty": 0.10},
            {"price": 45282.1, "qty": 0.20}
          ],
          "asks": [
            {"price": 45284.2, "qty": 0.30},
            {"price": 45285.0, "qty": 0.40}
          ],
          "checksum": 3039719286
        }
      ],
      "type": "snapshot"
    }
    """
    book_update = """
    {
      "channel": "book",
      "data": [
        {
          "symbol": "BTC/USD",
          "bids": [{"price": 45283.5, "qty": 0.00}],
          "asks": [{"price": 45284.2, "qty": 0.55}],
          "checksum": 1234567890,
          "timestamp": "2023-10-06T17:35:55.440295Z"
        }
      ],
      "type": "update"
    }
    """
    book_update_behind_the_touch = """
    {
      "channel": "book",
      "data": [
        {
          "symbol": "BTC/USD",
          "bids": [{"price": 45282.1, "qty": 0.99}],
          "asks": [],
          "checksum": 1234567890,
          "timestamp": "2023-10-06T17:35:56.440295Z"
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

        await self.feed.connect("ETH-USD", max_retries=0)

        # Assertions
        mock_connect.assert_called_once_with("wss://ws.kraken.com/v2")

    @patch("websockets.connect")
    async def test_reconnect_to_production_feed(self, mock_connect):
        await self.create_mock_websocket(mock_connect, [])

        await self.feed.connect("ETH-USD", max_retries=3)

        self.assertEqual(mock_connect.call_count, 4)

    @patch("websockets.connect")
    async def test_an_unstated_retry_budget_comes_from_parameters(
        self, mock_connect
    ):
        """
        The application passes neither, so leaving them out has to give
        the declared budget rather than a single attempt.
        """
        use_parameter_service(
            StaticParameterService(
                KrakenFeedParameters(
                    max_retries=2, retry_interval_in_seconds=0.1
                )
            )
        )
        self.addCleanup(use_parameter_service, StaticParameterService())
        await self.create_mock_websocket(mock_connect, [])

        await self.feed.connect("ETH-USD")

        self.assertEqual(3, mock_connect.call_count)

    @patch("websockets.connect")
    async def test_heartbeat_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.heartbeat_feed]
        )

        await self.feed.connect("ETH-USD", max_retries=0)

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

        await self.feed.connect("ETH-USD", max_retries=0)

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

        await self.feed.connect("ETH-USD", max_retries=0)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )

    @patch("websockets.connect")
    async def test_error_feed_reports_the_connection_as_lost(
        self, mock_connect
    ):
        await self.create_mock_websocket(
            mock_connect,
            [TestPublicFeed.error_feed, TestPublicFeed.subscribe_feed],
        )

        with (
            patch.object(self.feed, "add_issue") as mock_add_issue,
            patch.object(self.feed, "remove_issue") as mock_remove_issue,
            self.assertLogs(level="ERROR") as logs,
        ):
            await self.feed.connect("ETH-USD", max_retries=0)

        self.assertIn("get an error message", "".join(logs.output))
        mock_add_issue.assert_any_call(
            HeartbeatLevel.ERROR,
            PublicFeed.ErrorCode.CONNECTION_LOST.value,
        )
        mock_remove_issue.assert_any_call(
            PublicFeed.ErrorCode.CONNECTION_LOST.value
        )

    @patch("websockets.connect")
    async def test_match_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.trade_feed_1]
        )

        await self.feed.connect("ETH-USD", max_retries=0)

        # Assertions
        self.assertEqual(
            2, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(3, self.feed.events.market_trade.send.call_count)

    @patch("websockets.connect")
    async def test_match_feed_reconnect(self, mock_connect):
        # After reconnecting, application may receive trades that have
        # already been transmitted
        mock_websocket = await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.trade_feed_1,
                TestPublicFeed.trade_feed_2,
                TestPublicFeed.trade_feed_1,
            ],
        )

        await self.feed.connect("ETH-USD", max_retries=0)

        # Assertions
        self.assertEqual(
            4, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(6, self.feed.events.market_trade.send.call_count)

    @patch("websockets.connect")
    async def test_ticker_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.ticker_feed_1,
                TestPublicFeed.ticker_feed_3,
            ],
        )

        await self.feed.connect("ETH-USD", max_retries=0)

        # Assertions
        self.assertEqual(
            3, mock_websocket.__aenter__.return_value.recv.call_count
        )
        self.assertEqual(2, self.feed.events.ticker.send.call_count)

    @patch("websockets.connect")
    async def test_an_unchanged_touch_is_not_republished(self, mock_connect):
        await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.ticker_feed_1,
                TestPublicFeed.ticker_feed_2,
            ],
        )

        await self.feed.connect("ETH-USD", max_retries=0)

        self.assertEqual(1, self.feed.events.ticker.send.call_count)

    @patch("websockets.connect")
    async def test_book_feed(self, mock_connect):
        await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.book_snapshot,
                TestPublicFeed.book_update,
            ],
        )

        await self.feed.connect("BTC-USD", max_retries=0)

        self.assertEqual(2, self.feed.events.order_book.send.call_count)

        book = self.feed.events.order_book.send.call_args.kwargs["order_book"]
        self.assertEqual(
            [PriceLevel(45282.1, 0.20)],
            book.bids(10),
        )
        self.assertEqual(
            [PriceLevel(45284.2, 0.55), PriceLevel(45285.0, 0.40)],
            book.asks(10),
        )
        self.assertEqual(
            datetime.fromisoformat("2023-10-06T17:35:55.440295Z"),
            book.exchange_time,
        )

    @patch("websockets.connect")
    async def test_book_is_authoritative_for_the_touch(self, mock_connect):
        await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.book_snapshot,
                TestPublicFeed.ticker_feed_1,
            ],
        )

        await self.feed.connect("BTC-USD", max_retries=0)

        self.assertEqual(1, self.feed.events.ticker.send.call_count)
        bbo = self.feed.events.ticker.send.call_args.kwargs["bbo"]
        self.assertEqual(45283.5, bbo.bid_price)
        self.assertEqual(45284.2, bbo.ask_price)

    @patch("websockets.connect")
    async def test_ticker_fills_in_until_the_first_snapshot(
        self, mock_connect
    ):
        await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.ticker_feed_1,
                TestPublicFeed.book_snapshot,
            ],
        )

        await self.feed.connect("BTC-USD", max_retries=0)

        published = [
            call.kwargs["bbo"].bid_price
            for call in self.feed.events.ticker.send.call_args_list
        ]
        self.assertEqual([6000.0, 45283.5], published)

    @patch("websockets.connect")
    async def test_depth_behind_the_touch_does_not_requote(self, mock_connect):
        await self.create_mock_websocket(
            mock_connect,
            [
                TestPublicFeed.book_snapshot,
                TestPublicFeed.book_update_behind_the_touch,
            ],
        )

        await self.feed.connect("BTC-USD", max_retries=0)

        self.assertEqual(2, self.feed.events.order_book.send.call_count)
        self.assertEqual(1, self.feed.events.ticker.send.call_count)

    @patch("websockets.connect")
    async def test_unknown_feed(self, mock_connect):
        mock_websocket = await self.create_mock_websocket(
            mock_connect, [TestPublicFeed.unknown_feed]
        )

        await self.feed.connect("ETH-USD", max_retries=0)

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

        await self.feed.connect(
            "ETH-USD", max_retries=0, retry_interval_in_seconds=0
        )

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

    @patch("websockets.connect")
    async def test_receiver_bug_does_not_mislabel_or_break_connection(
        self, mock_connect
    ):
        self.feed.events.channel_heartbeat.send.side_effect = RuntimeError(
            "receiver bug"
        )
        await self.create_mock_websocket(
            mock_connect,
            [TestPublicFeed.heartbeat_feed, TestPublicFeed.heartbeat_feed],
        )

        with patch.object(self.feed, "add_issue") as mock_add_issue:
            await self.feed.connect("ETH-USD", max_retries=0)

        self.assertEqual(2, self.feed.events.channel_heartbeat.send.call_count)
        mock_add_issue.assert_not_called()

    @patch("websockets.connect")
    async def test_malformed_response_issue_clears_on_recovery(
        self, mock_connect
    ):
        malformed_ticker_feed = """
        {
          "channel": "ticker",
          "data": [],
          "type": "update"
        }
        """
        await self.create_mock_websocket(
            mock_connect,
            [malformed_ticker_feed, TestPublicFeed.heartbeat_feed],
        )

        with (
            patch.object(self.feed, "add_issue") as mock_add_issue,
            patch.object(self.feed, "remove_issue") as mock_remove_issue,
        ):
            await self.feed.connect(
                "ETH-USD", max_retries=1, retry_interval_in_seconds=0
            )

        mock_add_issue.assert_any_call(
            HeartbeatLevel.ERROR,
            PublicFeed.ErrorCode.MALFORMAT_RESPONSE.value,
        )
        mock_remove_issue.assert_any_call(
            PublicFeed.ErrorCode.MALFORMAT_RESPONSE.value
        )

    @patch("websockets.connect")
    async def test_retry_budget_resets_after_a_healthy_connection(
        self, mock_connect
    ):
        self.feed._clock = Mock(side_effect=[0, 100, 100, 100])
        await self.create_mock_websocket(
            mock_connect,
            [
                websockets.exceptions.ConnectionClosedError(
                    rcvd=None, sent=None
                ),
                websockets.exceptions.ConnectionClosedError(
                    rcvd=None, sent=None
                ),
            ],
        )

        await self.feed.connect(
            "ETH-USD", max_retries=0, retry_interval_in_seconds=0
        )

        self.assertEqual(2, mock_connect.call_count)


class TestBookChecksum(unittest.IsolatedAsyncioTestCase):
    """
    Kraken checksums the top ten levels of each side, rendered as strings
    at the pair's own decimal precision. The book and expected CRC32 below
    are the worked example from Kraken's own documentation.
    """

    DOCUMENTED_ASKS = [
        (45285.2, 0.00100000),
        (45286.4, 1.54571953),
        (45286.6, 1.54571109),
        (45289.6, 1.54560911),
        (45290.2, 0.15890660),
        (45291.8, 1.54553491),
        (45294.7, 0.04454749),
        (45296.1, 0.35380000),
        (45297.5, 0.09945542),
        (45299.5, 0.18772827),
    ]
    DOCUMENTED_BIDS = [
        (45283.5, 0.10000000),
        (45283.4, 1.54582015),
        (45282.1, 0.10000000),
        (45281.0, 0.10000000),
        (45280.3, 1.54592586),
        (45279.0, 0.07990000),
        (45277.6, 0.03310103),
        (45277.5, 0.30000000),
        (45277.3, 1.54602737),
        (45276.6, 0.15445238),
    ]
    DOCUMENTED_CHECKSUM = 3310070434

    INSTRUMENT = json.dumps(
        {
            "channel": "instrument",
            "type": "snapshot",
            "data": {
                "assets": [],
                "pairs": [
                    {
                        "symbol": "BTC/USD",
                        "price_precision": 1,
                        "qty_precision": 8,
                    }
                ],
            },
        }
    )

    @classmethod
    def book(cls, checksum: int) -> str:
        def levels(side):
            return [{"price": price, "qty": qty} for price, qty in side]

        return json.dumps(
            {
                "channel": "book",
                "type": "snapshot",
                "data": [
                    {
                        "symbol": "BTC/USD",
                        "bids": levels(cls.DOCUMENTED_BIDS),
                        "asks": levels(cls.DOCUMENTED_ASKS),
                        "checksum": checksum,
                    }
                ],
            }
        )

    async def asyncSetUp(self):
        self.feed = PublicFeed()
        self.feed.events = Mock()

    async def run_feed(self, mock_connect, feeds):
        mock_websocket = await TestPublicFeed.create_mock_websocket(
            mock_connect, feeds
        )
        await self.feed.connect("BTC/USD", max_retries=0)
        return mock_websocket

    def issues(self):
        return [issue.message for issue in self.feed._issues]

    @patch("websockets.connect")
    async def test_a_matching_checksum_keeps_the_book(self, mock_connect):
        await self.run_feed(
            mock_connect,
            [self.INSTRUMENT, self.book(self.DOCUMENTED_CHECKSUM)],
        )

        self.assertEqual(1, self.feed.events.order_book.send.call_count)
        self.assertNotIn(
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
            self.issues(),
        )

    @patch("websockets.connect")
    async def test_a_failed_checksum_rebuilds_the_book(self, mock_connect):
        mock_websocket = await self.run_feed(
            mock_connect, [self.INSTRUMENT, self.book(checksum=1)]
        )

        self.assertEqual(0, self.feed.events.order_book.send.call_count)
        self.assertEqual([], self.feed._order_book.bids(10))
        self.assertIn(
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
            self.issues(),
        )

        sent = mock_websocket.__aenter__.return_value.send
        methods = [
            json.loads(call.args[0])["method"] for call in sent.call_args_list
        ]
        self.assertEqual(["unsubscribe", "subscribe"], methods[-2:])

    @patch("websockets.connect")
    async def test_a_fresh_snapshot_clears_the_issue(self, mock_connect):
        await self.run_feed(
            mock_connect,
            [
                self.INSTRUMENT,
                self.book(checksum=1),
                self.book(self.DOCUMENTED_CHECKSUM),
            ],
        )

        self.assertNotIn(
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
            self.issues(),
        )
        self.assertEqual(1, self.feed.events.order_book.send.call_count)

    @patch("websockets.connect")
    async def test_no_precision_yet_means_no_verdict(self, mock_connect):
        await self.run_feed(mock_connect, [self.book(checksum=1)])

        self.assertEqual(1, self.feed.events.order_book.send.call_count)
        self.assertNotIn(
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
            self.issues(),
        )
