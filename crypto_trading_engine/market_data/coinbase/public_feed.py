import json
from dataclasses import dataclass
from enum import Enum

import websockets
from blinker import signal

from crypto_trading_engine.core.health_monitor.heartbeat import (
    Heartbeater,
    HeartbeatLevel,
)


class CoinbaseEnvironment(Enum):
    PRODUCTION = 1
    SANDBOX = 2


class CoinbasePublicFeed(Heartbeater):
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
        Summary of all supported events for Coinbase's websocket channels.

        See Also:
            https://docs.cloud.coinbase.com/exchange/docs/websocket-channels
        """

        channel_heartbeat = signal("heartbeat")
        ticker = signal("ticker")
        matches = signal("matches")

    def __init__(self, env: CoinbaseEnvironment = CoinbaseEnvironment.SANDBOX):
        super().__init__(type(self).__name__)
        self._env = env
        self._events = CoinbasePublicFeed.Events()

    async def connect(self, product_ids: list[str]):
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

                    elif response["type"] == "ticker":
                        self._events.channel_heartbeat.send(
                            self._events.channel_heartbeat, payload=response
                        )

                    elif response["type"] == "heartbeat":
                        self._events.ticker.send(
                            self._events.ticker, payload=response
                        )
                    else:
                        pass  # Ignore unsupported message types

                except websockets.exceptions.ConnectionClosedError:
                    self.add_issue(HeartbeatLevel.ERROR, "Connection Lost")
                    break
