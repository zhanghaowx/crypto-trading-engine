import asyncio
import json
import logging
import math
from datetime import datetime
from enum import Enum

import websockets

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class PublicFeed(Heartbeater):
    """
    Download Kraken's public market data using Websockets. This class
    implements the v2 version of Kraken's websocket API.

    See more: https://docs.kraken.com/websockets-v2/#introduction
    """

    PRODUCTION_URI = "wss://ws.kraken.com/v2"

    class ErrorCode(Enum):
        CONNECTION_LOST = "Connection Lost"
        MALFORMAT_RESPONSE = "Malformatted Response from Kraken"

    def __init__(self, candlestick_interval_in_seconds: int = 60):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = Events()
        self._last_received_trade_id = -math.inf
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )

    async def connect(
        self,
        symbol: str,
        max_retries: int = 3,
        retry_interval_in_seconds: int = 5,
    ):
        n_retries = 0
        while n_retries <= max_retries:
            try:
                await self.connect_once(symbol)
            except Exception as e:
                logging.warning(
                    "Schedule a reconnect after encountering an error "
                    f"while connecting to Kraken's websocket: {e}"
                )
                await asyncio.sleep(retry_interval_in_seconds)
            n_retries += 1

    async def connect_once(self, symbol: str):
        """Establish a connection to the remote service and subscribe to the
        public market data feed.

        Returns:
            An asyncio task to be waiting for incoming messages
        """

        async with websockets.connect(PublicFeed.PRODUCTION_URI) as websocket:

            async def subscribe_to_channel(channel_name: str):
                subscribe_message = {
                    "method": "subscribe",
                    "params": {
                        "channel": channel_name,
                        "snapshot": True,
                        "symbol": [symbol],
                    },
                    "req_id": id_generator().next(),
                }
                # Send the subscribe message as a JSON string
                await websocket.send(json.dumps(subscribe_message))

            # Trade channel pushes trades in real-time. Multiple trades may be
            # batched in a single message but that does not necessarily mean
            # that every trade in a single message resulted from a single taker
            # order.
            await subscribe_to_channel("trade")
            # Ticker channel pushes updates whenever there is a trade or there
            # is a change (price or quantity) at the top-of-book.
            await subscribe_to_channel("ticker")

            while True:
                try:
                    # Receive and process messages from WebSocket
                    data = await websocket.recv()
                    response = json.loads(data)

                    try:
                        self._decode_message(response)
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

    def _decode_message(self, response):
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
            self.events.channel_heartbeat.send(
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
                "Should only receive " "ticker feed for one symbol"
            )
            ticker_json = response["data"][0]
            self.events.ticker.send(
                self.events.ticker,
                bbo=BBO(
                    symbol=ticker_json["symbol"],
                    bid_price=ticker_json["bid"],
                    bid_quantity=ticker_json["bid_qty"],
                    ask_price=ticker_json["ask"],
                    ask_quantity=ticker_json["ask_qty"],
                ),
            )
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
                self.events.market_trade.send(
                    self.events.market_trade, market_trade=market_trade
                )
                self._last_received_trade_id = int(market_trade.trade_id)
                logging.debug("Received Market Trade: %s", market_trade)

                # Calculate our own candlesticks using market trades
                candlesticks = self._candlestick_generator.on_market_trade(
                    market_trade
                )
                for candlestick in candlesticks:
                    self.events.candlestick.send(
                        self.events.candlestick,
                        candlestick=candlestick,
                    )
