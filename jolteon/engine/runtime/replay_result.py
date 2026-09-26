"""Persist comparison outputs without incidental exchange or client IDs."""

import json

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.event.signal_recorder import SignalRecorder
from jolteon.engine.core.parameter.parameter_service import parameter_service
from jolteon.engine.core.time.time_manager import time_manager

OUTPUT_CHANNELS = (
    "fair_price",
    "fair_price_adjustment",
    "quote_offset",
    "order",
    "cancel_order",
    "order_fill",
    "position_updated",
)


class ReplayResult:
    def __init__(self, path):
        self.path = path
        self.orders: dict[str, int] = {}
        self.working: dict[int, dict] = {}
        self.counts = dict.fromkeys(OUTPUT_CHANNELS, 0)
        self._file = None
        self.market_context: dict = {}

    def start(self):
        self._file = self.path.open("x")
        for channel in OUTPUT_CHANNELS:
            signal(channel).connect(self._record)
        signal("bbo_feed").connect(self._bbo)
        signal("order_book_feed").connect(self._book)

    def close(self):
        for channel in OUTPUT_CHANNELS:
            signal(channel).disconnect(self._record)
        signal("bbo_feed").disconnect(self._bbo)
        signal("order_book_feed").disconnect(self._book)
        if self._file is not None:
            self._file.close()

    def _bbo(self, sender, bbo):
        self.market_context["bbo"] = SignalRecorder._to_dict(bbo)

    def _book(self, sender, order_book):
        self.market_context["book"] = {
            "bids": [
                [level.price, level.quantity] for level in order_book.bids(3)
            ],
            "asks": [
                [level.price, level.quantity] for level in order_book.asks(3)
            ],
        }

    def _record(self, sender, **kwargs):
        payload = SignalRecorder._to_dict(next(iter(kwargs.values())))
        channel = sender.name
        client = payload.get("client_order_id")
        if client is not None:
            if channel == "order":
                self.orders[client] = len(self.orders) + 1
            payload["client_order_id"] = self.orders[client]
        if channel == "order":
            self.working[payload["client_order_id"]] = dict(payload)
        elif channel == "cancel_order":
            self.working.pop(payload["client_order_id"], None)
        elif channel == "order_fill":
            for key in (
                "maker_order_id",
                "taker_order_id",
                "exchange_trade_id",
                "exchange_order_id",
                "exchange_execution_id",
                "unique_trade_id",
            ):
                payload.pop(key, None)
        self.counts[channel] += 1
        assert self._file is not None
        self._file.write(
            json.dumps(
                {
                    "channel": channel,
                    "timestamp": time_manager().now().timestamp(),
                    "payload": payload,
                    "market_context": self.market_context,
                    "parameter_revision": parameter_service()
                    .values()
                    .revision,
                },
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
