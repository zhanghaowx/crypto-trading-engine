"""Deliver validated external inputs on a paced simulated timeline."""

from datetime import datetime, timezone

from jolteon.engine.core.engine_run import MarketDataMode
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.replay_clock import Playback, ReplayClock
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order_book import (
    BookModel,
    OrderBook,
    RecordedBookUpdate,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed


class ManifestFeed(IMarketDataFeed):
    def __init__(
        self, manifest, recording, parameters, health_monitor, playback=None
    ):
        super().__init__(
            "ManifestFeed",
            interval_in_seconds=0,
            health_monitor=health_monitor,
        )
        self.manifest = manifest
        self.recording = recording
        self.parameters = parameters
        self.playback = playback or Playback(
            manifest.document["playback"]["speed"]
        )
        self.book = OrderBook("BTC/USD")
        self.delivered = 0

    @property
    def market_data_mode(self):
        return MarketDataMode.RECORDED

    @property
    def channels(self):
        return frozenset(Channel)

    async def connect(self, symbol: str, *args) -> None:
        manager = time_manager()
        manager.claim_admin(self)
        clock = ReplayClock(
            self.recording.events[0].timestamp,
            lambda now: manager.use_fake_time(now, admin=self),
        )
        try:
            clock.advance(clock.timestamp)
            for revision in self.recording.revisions:

                def apply(row=revision):
                    self.parameters.replace(row["parameters"], row["revision"])

                if revision["timestamp"] <= clock.timestamp:
                    apply()
                else:
                    clock.call_at(revision["timestamp"], apply)
            playback_started = False

            async def advance_playback(timestamp):
                nonlocal playback_started
                if not playback_started:
                    clock.advance(self.manifest.start)
                    await self.playback.pace(self.manifest.start)
                    playback_started = True
                await self.playback.advance(clock, timestamp)

            for event in self.recording.events:
                if event.timestamp < self.manifest.start:
                    clock.advance(event.timestamp)
                else:
                    await advance_playback(event.timestamp)
                self._deliver(event)
                self.delivered += 1
                # Drain zero-delay timers after the signal cascade returns.
                clock.advance(event.timestamp)
            # The external-event interval is half-open; timers include its end.
            await advance_playback(self.manifest.end)
        finally:
            clock.close()
            manager.reset(admin=self)

    def _deliver(self, event) -> None:
        payload = event.payload
        if event.channel == "instrument_feed":
            from jolteon.engine.market_data.core.instrument import (
                InstrumentSpec,
            )

            self.events.instrument.send(
                self.events.instrument, instrument=InstrumentSpec(**payload)
            )
        elif event.channel == "order_book_update_feed":
            record = RecordedBookUpdate(
                **{
                    **payload,
                    "model": BookModel(payload["model"]),
                    "exchange_time": datetime.fromtimestamp(
                        payload["exchange_time"], timezone.utc
                    ),
                }
            )
            self.book.apply(record.to_update())
            self.events.order_book_update.send(
                self.events.order_book_update, book_update=record
            )
            self.events.order_book.send(
                self.events.order_book, order_book=self.book
            )
        elif event.channel == "bbo_feed":
            if (
                event.timestamp >= self.manifest.start
                and self.book.bbo() is not None
            ):
                self.mark_healthy()
            self.events.bbo.send(self.events.bbo, bbo=BBO(**payload))
        else:
            trade = Trade(
                exchange_trade_id=payload["exchange_trade_id"],
                client_order_id="",
                symbol=payload["symbol"],
                maker_order_id="",
                taker_order_id="",
                side=MarketSide.parse(payload["side"]),
                price=payload["price"],
                fee=0.0,
                quantity=payload["quantity"],
                transaction_time=datetime.fromtimestamp(
                    payload["transaction_time"], timezone.utc
                ),
            )
            self.events.market_trade.send(
                self.events.market_trade, market_trade=trade
            )
