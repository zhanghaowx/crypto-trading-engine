import json
import logging
from datetime import datetime
from enum import Enum

import websockets

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class PublicFeed(Heartbeater):
    """
    Download Kraken's public market data using Websockets. This class
    implements the v2 version of Kraken's websocket API.
    """

    PRODUCTION_URI = "wss://ws.kraken.com/v2"

    def __init__(self, candlestick_interval_in_seconds: int = 60):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = Events()
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )

    async def connect(self, symbol: str):
        """Establish a connection to the remote service and subscribe to the
        public market data feed.

        Returns:
            An asyncio task to be waiting for incoming messages
        """

        async with websockets.connect(PublicFeed.PRODUCTION_URI) as websocket:
            # Trade channel pushes trades in real-time. Multiple trades may be
            # batched in a single message but that does not necessarily mean
            # that every trade in a single message resulted from a single taker
            # order.
            subscribe_message = {
                "method": "subscribe",
                "params": {
                    "channel": "trade",
                    "snapshot": True,
                    "symbol": [symbol],
                },
                "req_id": id_generator().next(),
            }

            # Send the subscribe message as a JSON string
            await websocket.send(json.dumps(subscribe_message))

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
                        self.add_issue(HeartbeatLevel.ERROR, f"{e}")
                except websockets.exceptions.ConnectionClosedError as e:
                    self.add_issue(HeartbeatLevel.ERROR, "Connection Lost")
                    logging.error(f"Connection Closed: {e}", exc_info=True)
                    break
                except StopAsyncIteration:
                    break

        logging.warning(
            "Encountered exception: shutting down market data feed!"
        )

    def _decode_message(self, response):
        class ErrorCode(Enum):
            CONNECTION_LOST = "Connection Lost"

        possible_error = response.get("error")
        if possible_error:
            logging.error(
                f"Encountered error: {possible_error}", exc_info=True
            )
            self.add_issue(
                HeartbeatLevel.ERROR, ErrorCode.CONNECTION_LOST.value
            )
            return

        possible_method = response.get("method")
        if possible_method == "pong":
            return
        elif possible_method == "subscribe":
            self.remove_issue(ErrorCode.CONNECTION_LOST.value)
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
                market_trade = Trade(
                    trade_id=trade_json["trade_id"],
                    client_order_id="",
                    symbol=trade_json["symbol"],
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide(trade_json["side"].upper()),
                    price=float(trade_json["price"]),
                    quantity=float(trade_json["qty"]),
                    transaction_time=datetime.fromisoformat(
                        trade_json["timestamp"]
                    ),
                )
                self.events.matches.send(
                    self.events.matches, market_trade=market_trade
                )
                logging.debug(f"Received Market Trade: {market_trade}")

                # Calculate our own candlesticks using market trades
                candlesticks = self._candlestick_generator.on_market_trade(
                    market_trade
                )
                for candlestick in candlesticks:
                    self.events.candlestick.send(
                        self.events.candlestick,
                        candlestick=candlestick,
                    )
