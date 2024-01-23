import asyncio
import logging
from datetime import datetime
from enum import Enum

from kraken.spot import KrakenSpotWSClientV2

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class PublicFeed(Heartbeater):
    def __init__(self, candlestick_interval_in_seconds: int = 60):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = Events()
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )
        self._client = KrakenSpotWSClientV2(callback=self.on_message)
        self._exception_occurred = False

    def connect(self, symbol: str):
        # Create a new event loop for the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the first async task with arguments in the event loop
        try:
            loop.run_until_complete(self.async_connect(symbol))
        except asyncio.CancelledError:
            pass  # Ignore CancelledError on cleanup
        except Exception as e:
            logging.error(
                f"Public feed connect task exception: {e}", exc_info=True
            )

    async def async_connect(self, symbol: str):
        """Establish a connection to the remote service and subscribe to the
        public market data feed.

        Returns:
            An asyncio task to be waiting for incoming messages
        """

        # Trade channel pushes trades in real-time. Multiple trades may be
        # batched in a single message but that does not necessarily mean that
        # every trade in a single message resulted from a single taker order.
        await self._client.subscribe(
            params={"channel": "trade", "symbol": [symbol]}
        )

        while not self._exception_occurred:
            await asyncio.sleep(10)

        logging.error("Encountered exception: shutting down market data feed!")

    async def on_message(self, message):
        try:
            self._decode_message(message)
        except Exception as e:
            logging.error(
                f"Error '{e}' when decoding message '{message}'", exc_info=True
            )
            self.add_issue(HeartbeatLevel.ERROR, f"{e}")
            self._exception_occurred = True

    def _decode_message(self, response):
        class Error(Enum):
            CONNECTION_LOST = "Connection Lost"

        possible_error = response.get("error")
        if possible_error:
            logging.error(
                f"Encountered error: {possible_error}", exc_info=True
            )
            self.add_issue(HeartbeatLevel.ERROR, Error.CONNECTION_LOST.value)
            return

        possible_method = response.get("method")
        if possible_method == "pong":
            logging.error(f"Pong message: {response}")
            return
        elif possible_method == "subscribe":
            self.remove_issue(Error.CONNECTION_LOST.value)
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
