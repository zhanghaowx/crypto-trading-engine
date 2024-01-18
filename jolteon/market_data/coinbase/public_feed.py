import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import websockets
from blinker import signal

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.trade import Trade


class CoinbaseEnvironment(Enum):
    PRODUCTION = 1
    SANDBOX = 2


class PublicFeed(Heartbeater):
    """
    Coinbase's webSocket feed is publicly available and provides real-time
    market data updates for orders and trades.

    Note:
        New message types can be added at any time. Clients are expected to
        ignore messages they do not support.

    See more:
        https://docs.cloud.coinbase.com/exchange/docs/websocket-overview

    Todo:
        1. Level2 Channel Support (Requires Authentication)
        2. Use Thread or Process to Offload Work
        3. Gap Recovery
        4. Fail Over
        5. Data Compression
    """

    @dataclass
    class Events:
        """
        Summary of all supported events for Coinbase's websocket channels,
        as well as events calculated from Coinbase's native events.

        See Also:
            https://docs.cloud.coinbase.com/exchange/docs/websocket-channels
        """

        channel_heartbeat = signal("channel_heartbeat_feed")
        ticker = signal("ticker_feed")
        matches = signal("matches_feed")
        candlestick = signal("calculated_candlestick_feed")

    def __init__(
        self,
        env: CoinbaseEnvironment = CoinbaseEnvironment.SANDBOX,
        candlestick_interval_in_seconds: int = 60,
    ):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = PublicFeed.Events()
        self._env = env
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )

    async def connect(self, product_ids: list[str]):
        """
        Establish a connection to the remote service and subscribe to the
        public market data feed.

        Args:
            product_ids: A list of product ids(symbols) to subscribe to.
        Returns:
            An asyncio task to be waiting for incoming messages
        """
        production_uri = "wss://ws-feed.exchange.coinbase.com"
        sandbox_uri = "wss://ws-feed-public.sandbox.exchange.coinbase.com"

        # Pick URI based on the environment
        if self._env == CoinbaseEnvironment.PRODUCTION:
            uri = production_uri
        else:
            uri = sandbox_uri

        async with websockets.connect(uri) as websocket:
            # Define the message to subscribe to a specific product's channel
            subscribe_message = {
                "type": "subscribe",
                "product_ids": product_ids,
                "channels": ["heartbeat", "ticker", "matches"],
            }

            # Send the subscribe message as a JSON string
            await websocket.send(json.dumps(subscribe_message))

            while True:
                try:
                    # Receive and process messages from WebSocket
                    data = await websocket.recv()
                    response = json.loads(data)

                    # As of now treat errors as unrecoverable
                    if response["type"] == "error":
                        self.add_issue(
                            HeartbeatLevel.ERROR, response["reason"]
                        )
                        break

                    elif response["type"] == "subscriptions":
                        pass

                    elif response["type"] == "heartbeat":
                        self.events.channel_heartbeat.send(
                            self.events.channel_heartbeat, payload=response
                        )
                        self.send_heartbeat()

                    elif response["type"] == "ticker":
                        self.events.ticker.send(
                            self.events.ticker, payload=response
                        )
                    elif response["type"] == "match":
                        """
                        Below is an example of one match message from Coinbase
                        ```
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
                        ```
                        """

                        market_trade = Trade(
                            trade_id=response["trade_id"],
                            client_order_id="",
                            symbol=response["product_id"],
                            maker_order_id=response["maker_order_id"],
                            taker_order_id=response["taker_order_id"],
                            side=MarketSide(response["side"].upper()),
                            price=float(response["price"]),
                            quantity=float(response["size"]),
                            transaction_time=datetime.fromisoformat(
                                response["time"]
                            ),
                        )
                        self.events.matches.send(
                            self.events.matches, market_trade=market_trade
                        )
                        logging.debug(f"Received Market Trade: {market_trade}")

                        candlesticks = (
                            self._candlestick_generator.on_market_trade(
                                market_trade
                            )
                        )
                        for candlestick in candlesticks:
                            self.events.candlestick.send(
                                self.events.candlestick,
                                candlestick=candlestick,
                            )
                    else:
                        pass  # Ignore unsupported message types

                except websockets.exceptions.ConnectionClosedError:
                    self.add_issue(HeartbeatLevel.ERROR, "Connection Lost")
                    break
