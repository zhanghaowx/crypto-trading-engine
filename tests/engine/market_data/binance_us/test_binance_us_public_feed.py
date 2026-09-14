import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from websockets.exceptions import ConnectionClosedError

from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
    use_parameter_service,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.binance_us.parameters import (
    BinanceUsFeedParameters,
)
from jolteon.engine.market_data.binance_us.public_feed import (
    PublicFeed,
    _precision,
)
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed

INFO = {
    "symbols": [
        {
            "symbol": "BTCUSD",
            "baseAsset": "BTC",
            "quoteAsset": "USD",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {
                    "filterType": "LOT_SIZE",
                    "stepSize": "0.00001000",
                    "minQty": "0.00010000",
                },
                {"filterType": "MIN_NOTIONAL", "minNotional": "1.00"},
            ],
        }
    ]
}
SNAPSHOT = {
    "lastUpdateId": 10,
    "bids": [["99", "2"]],
    "asks": [["101", "3"]],
}


class TestPublicFeed(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        use_parameter_service(StaticParameterService())
        self.rest = Mock()
        self.rest.exchange_info.return_value = INFO
        self.rest.depth.return_value = SNAPSHOT
        self.feed = PublicFeed(self.rest)
        self.feed._symbol = "BTC/USD"
        self.feed._wire_symbol = "btcusd"
        self.feed._book_depth = 1000

    def test_declares_every_public_channel_and_encodes_symbols(self):
        self.assertEqual(
            {
                Channel.MARKET_TRADE,
                Channel.TICKER,
                Channel.ORDER_BOOK,
                Channel.INSTRUMENT,
            },
            set(self.feed.channels),
        )
        self.assertEqual("btcusd", PublicFeed.encode_symbol("BTC/USD"))
        self.assertEqual("btcusd", PublicFeed.encode_symbol("BTC-USD"))

    def test_decodes_exchange_filters(self):
        instrument = self.feed._decode_instrument(INFO["symbols"][0])

        self.assertEqual("BTC/USD", instrument.symbol)
        self.assertEqual(0.01, instrument.price_increment)
        self.assertEqual(2, instrument.price_precision)
        self.assertEqual(5, instrument.qty_precision)
        self.assertEqual(0.0001, instrument.qty_min)
        self.assertEqual(1.0, instrument.cost_min)
        self.assertEqual(0, _precision("0"))

    async def test_publishes_instrument_before_market_data(self):
        seen = []

        def receiver(_, instrument):
            seen.append(instrument)

        self.feed.events.instrument.connect(receiver, weak=False)

        await self.feed._publish_instrument()

        self.assertEqual(["BTC/USD"], [item.symbol for item in seen])
        self.rest.exchange_info.assert_called_once_with("BTCUSD")

    async def test_rejects_missing_instrument_rules(self):
        self.rest.exchange_info.return_value = {"symbols": []}
        with self.assertRaisesRegex(ValueError, "No Binance.US rules"):
            await self.feed._publish_instrument()

    async def test_loads_snapshot_and_applies_contiguous_depth(self):
        books = []

        def receiver(_, order_book):
            books.append(order_book.bbo())

        self.feed.events.order_book.connect(receiver, weak=False)
        await self.feed._load_snapshot()

        await self.feed._apply_depth(
            {
                "e": "depthUpdate",
                "E": 1700000000000,
                "U": 11,
                "u": 12,
                "b": [["99", "4"]],
                "a": [["101", "0"], ["102", "5"]],
            }
        )

        self.assertEqual(12, self.feed._last_update_id)
        self.assertEqual(4.0, books[0].bid_quantity)
        self.assertEqual(102.0, books[0].ask_price)

    async def test_ignores_updates_already_in_snapshot(self):
        await self.feed._load_snapshot()
        await self.feed._apply_depth({"U": 8, "u": 10, "b": [], "a": []})
        self.assertEqual(10, self.feed._last_update_id)

    async def test_gap_clears_book_and_requests_fresh_snapshot(self):
        await self.feed._load_snapshot()
        with patch.object(
            self.feed, "resync_order_book", AsyncMock()
        ) as resync:
            await self.feed._apply_depth({"U": 15, "u": 16, "b": [], "a": []})
        resync.assert_awaited_once_with(self.feed._order_book)

    async def test_resync_stays_degraded_until_a_bridging_update(self):
        await self.feed._request_order_book_snapshot("BTC/USD")
        self.feed.add_issue(
            HeartbeatLevel.WARN,
            IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name,
        )

        await self.feed._apply_depth(
            {"U": 10, "u": 11, "b": [["99", "4"]], "a": []}
        )

        self.assertFalse(self.feed._awaiting_bridge)
        self.assertTrue(
            all(
                issue.message
                != IMarketDataFeed.ErrorCode.ORDER_BOOK_OUT_OF_SYNC.name
                for issue in self.feed._issues
            )
        )

    async def test_requires_snapshot_before_depth(self):
        with self.assertRaisesRegex(AssertionError, "Snapshot must load"):
            await self.feed._apply_depth({"U": 1, "u": 1, "b": [], "a": []})

    async def test_decodes_trade_touch_and_unknown_message(self):
        trades, ticks = [], []

        def trade_receiver(_, market_trade):
            trades.append(market_trade)

        def tick_receiver(_, bbo):
            ticks.append(bbo)

        self.feed.events.market_trade.connect(trade_receiver, weak=False)
        self.feed.events.ticker.connect(tick_receiver, weak=False)

        await self.feed._decode_message(
            {
                "stream": "btcusd@trade",
                "data": {
                    "e": "trade",
                    "t": 7,
                    "p": "100.5",
                    "q": "0.2",
                    "T": 1700000000000,
                    "m": True,
                },
            }
        )
        await self.feed._decode_message(
            {"b": "100", "B": "2", "a": "101", "A": "3"}
        )
        with self.assertLogs(level="INFO"):
            await self.feed._decode_message({"result": None})

        self.assertEqual(MarketSide.SELL, trades[0].side)
        self.assertEqual(7, trades[0].trade_id)
        self.assertEqual(100.0, ticks[0].bid_price)

    async def test_buyer_initiated_trade_is_a_buy(self):
        trades = []

        def receiver(_, market_trade):
            trades.append(market_trade)

        self.feed.events.market_trade.connect(receiver, weak=False)
        await self.feed._decode_message(
            {
                "e": "trade",
                "t": 8,
                "p": "100",
                "q": "1",
                "T": 1700000000000,
                "m": False,
            }
        )
        self.assertEqual(MarketSide.BUY, trades[0].side)

    async def test_server_shutdown_forces_reconnect(self):
        with self.assertRaisesRegex(ConnectionError, "shutting down"):
            await self.feed._decode_message({"e": "serverShutdown"})

    async def test_connect_once_builds_combined_stream_and_decodes(self):
        ws = AsyncMock()
        ws.recv.side_effect = [
            '{"data":{"b":"100","B":"2","a":"101","A":"3"}}',
            StopAsyncIteration,
        ]
        context = AsyncMock()
        context.__aenter__.return_value = ws
        context.__aexit__.return_value = False
        with patch("websockets.connect", return_value=context) as connect:
            await self.feed.connect_once("BTC/USD")

        uri = connect.call_args.args[0]
        self.assertIn("btcusd@trade", uri)
        self.assertIn("btcusd@bookTicker", uri)
        self.assertIn("btcusd@depth@100ms", uri)
        self.assertEqual(10, self.feed._last_update_id)

    async def test_connect_once_propagates_closed_connection(self):
        ws = AsyncMock()
        ws.recv.side_effect = ConnectionClosedError(None, None)
        context = AsyncMock()
        context.__aenter__.return_value = ws
        context.__aexit__.return_value = False
        with (
            patch("websockets.connect", return_value=context),
            self.assertRaises(ConnectionClosedError),
        ):
            await self.feed.connect_once("BTC/USD")

    async def test_connect_once_reports_malformed_message(self):
        ws = AsyncMock()
        ws.recv.return_value = "not-json"
        context = AsyncMock()
        context.__aenter__.return_value = ws
        context.__aexit__.return_value = False
        with (
            patch("websockets.connect", return_value=context),
            self.assertLogs(level="ERROR"),
            self.assertRaises(ValueError),
        ):
            await self.feed.connect_once("BTC/USD")

    async def test_connect_retries_and_preserves_cancellation(self):
        self.feed.connect_once = AsyncMock(
            side_effect=[RuntimeError("lost"), None]
        )
        with patch("asyncio.sleep", AsyncMock()):
            await self.feed.connect.__wrapped__(self.feed, "BTC/USD", 0, 0.1)
        self.assertEqual(1, self.feed.connect_once.await_count)

        self.feed.connect_once = AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await self.feed.connect.__wrapped__(self.feed, "BTC/USD", 0, 0.1)

    async def test_healthy_connection_resets_retries(self):
        self.feed.connect_once = AsyncMock(
            side_effect=[RuntimeError("lost"), None, asyncio.CancelledError]
        )
        self.feed._was_connection_healthy = Mock(side_effect=[False, True])
        with patch("asyncio.sleep", AsyncMock()):
            with self.assertRaises(asyncio.CancelledError):
                await self.feed.connect.__wrapped__(
                    self.feed, "BTC/USD", 1, 0.1
                )

        self.assertEqual(3, self.feed.connect_once.await_count)

    async def test_depth_messages_are_dispatched_through_decoder(self):
        await self.feed._load_snapshot()
        with patch.object(self.feed, "_apply_depth", AsyncMock()) as apply:
            await self.feed._decode_message(
                {"e": "depthUpdate", "U": 11, "u": 11, "b": [], "a": []}
            )
        apply.assert_awaited_once()

    def test_healthy_connection_resets_retry_budget(self):
        use_parameter_service(
            StaticParameterService(
                BinanceUsFeedParameters(min_healthy_connection_seconds=1)
            )
        )
        self.feed._clock = Mock(return_value=2)
        self.assertTrue(self.feed._was_connection_healthy(0, "BTC/USD"))
