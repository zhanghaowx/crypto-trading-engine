import asyncio
import json
import logging
import math
import time
import zlib
from datetime import datetime
from enum import Enum

import websockets

from jolteon.engine.core.health_monitor.heartbeat import (
    HeartbeatLevel,
    starts_heartbeating,
)
from jolteon.engine.core.id_generator import id_generator
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed


class PublicFeed(IMarketDataFeed):
    """
    Download Kraken's public market data using Websockets. This class
    implements the v2 version of Kraken's websocket API.

    See more: https://docs.kraken.com/websockets-v2/#introduction
    """

    PRODUCTION_URI = "wss://ws.kraken.com/v2"
    MIN_HEALTHY_CONNECTION_SECONDS = 60
    BOOK_DEPTH = 10
    # Kraken always checksums ten levels a side, whatever depth is
    # subscribed to.
    CHECKSUM_DEPTH = 10

    class ErrorCode(Enum):
        CONNECTION_LOST = "Connection Lost"
        MALFORMAT_RESPONSE = "Malformatted Response from Kraken"

    def __init__(self):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self._last_received_trade_id = -math.inf
        self._clock = time.monotonic
        self._order_book = OrderBook("")
        self._last_bbo: BBO | None = None
        self._price_precision: dict[str, int] = {}
        self._qty_precision: dict[str, int] = {}
        self._websocket: websockets.WebSocketClientProtocol | None = None

    @property
    def channels(self) -> frozenset[Channel]:
        return frozenset(
            {Channel.MARKET_TRADE, Channel.TICKER, Channel.ORDER_BOOK}
        )

    @starts_heartbeating
    async def connect(
        self,
        symbol: str,
        max_retries: int = 3,
        retry_interval_in_seconds: int = 5,
    ):
        n_retries = 0
        while n_retries <= max_retries:
            connected_at = self._clock()
            try:
                await self.connect_once(symbol)
            except Exception as e:
                logging.warning(
                    "Schedule a reconnect after encountering an error "
                    f"while connecting to Kraken's websocket: {e}"
                )
                await asyncio.sleep(retry_interval_in_seconds)

            if self._was_connection_healthy(connected_at):
                n_retries = 0
            else:
                n_retries += 1

    def _was_connection_healthy(self, connected_at: float) -> bool:
        return (
            self._clock() - connected_at
            >= PublicFeed.MIN_HEALTHY_CONNECTION_SECONDS
        )

    async def connect_once(self, symbol: str):
        """Establish a connection to the remote service and subscribe to the
        public market data feed.

        Returns:
            An asyncio task to be waiting for incoming messages
        """

        self._order_book = OrderBook(symbol)
        self._last_bbo = None

        async with websockets.connect(PublicFeed.PRODUCTION_URI) as websocket:
            self._websocket = websocket

            # Trade channel pushes trades in real-time. Multiple trades may be
            # batched in a single message but that does not necessarily mean
            # that every trade in a single message resulted from a single taker
            # order.
            await self._subscribe("trade", symbol=[symbol])
            # Ticker channel pushes updates whenever there is a trade or there
            # is a change (price or quantity) at the top-of-book.
            await self._subscribe("ticker", symbol=[symbol])
            # Instrument channel carries the decimal precision every book
            # checksum has to be rendered at. It covers all pairs, so it
            # takes no symbol.
            await self._subscribe("instrument")
            # Book channel pushes one snapshot followed by incremental
            # updates to the levels behind the touch.
            await self._subscribe(
                "book", symbol=[symbol], depth=PublicFeed.BOOK_DEPTH
            )

            while True:
                try:
                    # Receive and process messages from WebSocket
                    data = await websocket.recv()
                    response = json.loads(data)

                    try:
                        await self._decode_message(response)
                    except Exception as e:
                        logging.error(
                            f"Error '{e}' when decoding message '{response}'",
                            exc_info=True,
                        )
                        self.add_issue(
                            HeartbeatLevel.ERROR,
                            PublicFeed.ErrorCode.MALFORMAT_RESPONSE.value,
                        )
                        break
                    else:
                        self.remove_issue(
                            PublicFeed.ErrorCode.MALFORMAT_RESPONSE.value
                        )
                except websockets.exceptions.ConnectionClosedError as e:
                    self.add_issue(
                        HeartbeatLevel.ERROR,
                        PublicFeed.ErrorCode.CONNECTION_LOST.value,
                    )
                    logging.error(f"Connection Closed: {e}", exc_info=True)
                    raise e
                except StopAsyncIteration:
                    break

        return False

    def _dispatch_isolating_receiver_errors(self, signal, **kwargs):
        try:
            signal.send(signal, **kwargs)
        except Exception as e:
            logging.error(
                f"A receiver of signal '{signal.name}' raised an "
                f"exception: {e}",
                exc_info=True,
            )

    async def _subscribe(self, channel_name: str, **params) -> None:
        await self._send_request("subscribe", channel_name, **params)

    async def _unsubscribe(self, channel_name: str, **params) -> None:
        await self._send_request("unsubscribe", channel_name, **params)

    async def _send_request(
        self, method: str, channel_name: str, **params
    ) -> None:
        assert self._websocket, "Not connected to Kraken"
        await self._websocket.send(
            json.dumps(
                {
                    "method": method,
                    "params": {
                        "channel": channel_name,
                        "snapshot": True,
                        **params,
                    },
                    "req_id": id_generator().next(),
                }
            )
        )

    async def _request_order_book_snapshot(self, symbol: str) -> None:
        # Kraken rejects a repeat subscribe to a live channel, so the old
        # subscription has to go before a fresh snapshot can be asked for.
        await self._unsubscribe(
            "book", symbol=[symbol], depth=PublicFeed.BOOK_DEPTH
        )
        await self._subscribe(
            "book", symbol=[symbol], depth=PublicFeed.BOOK_DEPTH
        )

    def _is_book_in_sync(self, checksum: int | None) -> bool:
        """
        Returns: Whether the book still matches Kraken's, which can only
        be answered once the instrument channel has said what precision
        this pair renders at.
        """
        symbol = self._order_book.symbol
        if checksum is None or symbol not in self._price_precision:
            return True

        return self._book_checksum(symbol) == checksum

    def _book_checksum(self, symbol: str) -> int:
        depth = PublicFeed.CHECKSUM_DEPTH
        payload = "".join(
            self._render(level.price, self._price_precision[symbol])
            + self._render(level.quantity, self._qty_precision[symbol])
            for level in self._order_book.asks(depth)
            + self._order_book.bids(depth)
        )
        return zlib.crc32(payload.encode())

    @staticmethod
    def _render(value: float, precision: int) -> str:
        # Kraken checksums the digits as it rendered them, so the decimals
        # a float lost on the way in have to be put back before the point
        # is dropped and leading zeros stripped.
        return f"{value:.{precision}f}".replace(".", "").lstrip("0")

    def _decode_book_update(self, book_json, is_snapshot: bool) -> BookUpdate:
        timestamp = book_json.get("timestamp")
        return BookUpdate(
            symbol=book_json["symbol"],
            bids=[
                PriceLevel(float(level["price"]), float(level["qty"]))
                for level in book_json["bids"]
            ],
            asks=[
                PriceLevel(float(level["price"]), float(level["qty"]))
                for level in book_json["asks"]
            ],
            is_snapshot=is_snapshot,
            exchange_time=(
                datetime.fromisoformat(timestamp)
                if timestamp
                else time_manager().now()
            ),
        )

    def _publish_bbo(self, bbo: BBO | None) -> None:
        if not bbo or bbo == self._last_bbo:
            return

        self._last_bbo = bbo
        self._dispatch_isolating_receiver_errors(self.events.ticker, bbo=bbo)

    async def _decode_message(self, response):
        possible_error = response.get("error")
        if possible_error:
            logging.error(
                f"Encountered error: {possible_error}", exc_info=True
            )
            self.add_issue(
                HeartbeatLevel.ERROR,
                PublicFeed.ErrorCode.CONNECTION_LOST.value,
            )
            return

        possible_method = response.get("method")
        if possible_method == "pong":
            return
        elif possible_method == "subscribe":
            self.remove_issue(PublicFeed.ErrorCode.CONNECTION_LOST.value)
            return

        message_type = response.get("channel")
        if not message_type:
            logging.info(f"Ignoring message with no channel: {response}")
            return

        if message_type == "heartbeat":
            # Once subscribed to at least one channel, heartbeat messages are
            # sent approximately once every second in the absence of
            # subscription data.
            self._dispatch_isolating_receiver_errors(
                self.events.channel_heartbeat, payload=response
            )
        elif message_type == "ticker":
            """
            Below is an example of 2 ticker messages from Kraken:
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
            assert len(response["data"]) == 1, (
                "Should only receive ticker feed for one symbol"
            )
            ticker_json = response["data"][0]
            # The book is the authoritative view of the touch on this feed.
            # Ticker only fills the gap before the first book snapshot, and
            # again while a desynced book is being rebuilt; otherwise the
            # two views disagree transiently and BBO consumers see the
            # touch flicker between them.
            if not self._order_book.bbo():
                self._publish_bbo(
                    BBO(
                        symbol=ticker_json["symbol"],
                        bid_price=ticker_json["bid"],
                        bid_quantity=ticker_json["bid_qty"],
                        ask_price=ticker_json["ask"],
                        ask_quantity=ticker_json["ask_qty"],
                    )
                )
        elif message_type == "instrument":
            """
            The instrument channel carries the decimal precision each pair
            is quoted at, which a book checksum has to be rendered at:
            {
              "channel": "instrument",
              "data": {
                "assets": [],
                "pairs": [
                  {
                    "symbol": "BTC/USD",
                    "price_precision": 1,
                    "qty_precision": 8
                  }
                ]
              },
              "type": "snapshot"
            }
            """
            for pair_json in response["data"].get("pairs", []):
                symbol = pair_json["symbol"]
                self._price_precision[symbol] = pair_json["price_precision"]
                self._qty_precision[symbol] = pair_json["qty_precision"]
        elif message_type == "book":
            """
            Below is an example of a book message from Kraken. A snapshot
            carries the whole book to the subscribed depth, an update
            carries only the levels that changed, and a quantity of zero
            means the level is gone:
            {
              "channel": "book",
              "data": [
                {
                  "symbol": "BTC/USD",
                  "bids": [{"price": 45283.5, "qty": 0.10000000}],
                  "asks": [{"price": 45284.2, "qty": 0.00000000}],
                  "checksum": 3039719286,
                  "timestamp": "2023-10-06T17:35:55.440295Z"
                }
              ],
              "type": "update"
            }
            """
            is_snapshot = response.get("type") == "snapshot"
            for book_json in response["data"]:
                self._order_book.apply(
                    self._decode_book_update(book_json, is_snapshot)
                )
                if is_snapshot:
                    self.on_order_book_synced()

                if not self._is_book_in_sync(book_json.get("checksum")):
                    await self.resync_order_book(self._order_book)
                    return

                self._dispatch_isolating_receiver_errors(
                    self.events.order_book, order_book=self._order_book
                )
                self._publish_bbo(self._order_book.bbo())
        elif message_type == "trade":
            """
            Below is an example of one trade message from Kraken:
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
            for trade_json in response["data"]:
                # Test if these trades are replay trades after re-connecting
                # Note: Kraken's trade id is numerical
                trade_id = int(trade_json["trade_id"])
                if trade_id < self._last_received_trade_id:
                    continue

                market_trade = Trade(
                    trade_id=trade_json["trade_id"],
                    client_order_id="",
                    symbol=trade_json["symbol"],
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide(trade_json["side"].upper()),
                    price=float(trade_json["price"]),
                    fee=0.0,
                    quantity=float(trade_json["qty"]),
                    transaction_time=datetime.fromisoformat(
                        trade_json["timestamp"]
                    ),
                )
                self._dispatch_isolating_receiver_errors(
                    self.events.market_trade, market_trade=market_trade
                )
                self._last_received_trade_id = int(market_trade.trade_id)
                logging.debug("Received Market Trade: %s", market_trade)
