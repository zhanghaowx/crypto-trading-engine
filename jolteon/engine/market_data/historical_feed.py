import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto

from jolteon.engine.core.engine_run import MarketDataMode
from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.health_monitor.heartbeat import (
    starts_heartbeating,
)
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.order_book import OrderBook
from jolteon.engine.market_data.data_source import IDataSource
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed


class HistoricalFeed(IMarketDataFeed):
    @dataclass
    class ErrorCode(StrEnum):
        DOWNLOADING = auto()

    """
    Download and replay the historical market data feed.
    """

    def __init__(
        self,
        data_source: IDataSource,
        health_monitor: HealthMonitor | None = None,
    ):
        super().__init__(type(self).__name__, health_monitor=health_monitor)
        self._data_source = data_source

    @property
    def market_data_mode(self) -> MarketDataMode:
        return MarketDataMode.RECORDED

    @property
    def channels(self) -> frozenset[Channel]:
        return frozenset({Channel.MARKET_TRADE, Channel.ORDER_BOOK})

    @starts_heartbeating
    async def connect(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ):
        """
        Download the historical market data feed for the given symbol and
        time frame, and replay its trades.
        Args:
            symbol: Symbol of the product to download historical market data
            start_time: Start time of the historical market data feed.
            end_time: End time of the historical market data feed.
        Returns:
            A asyncio task to be waiting for incoming messages
        """
        time_manager().claim_admin(self)
        time_manager().use_fake_time(start_time, admin=self)

        self.add_issue(
            HealthState.WARNING, HistoricalFeed.ErrorCode.DOWNLOADING.name
        )
        market_trades = await self._data_source.download_market_trades(
            symbol, start_time, end_time
        )
        book_updates = await self._data_source.download_order_book_updates(
            symbol, start_time, end_time
        )
        self.remove_issue(HistoricalFeed.ErrorCode.DOWNLOADING.name)
        self.mark_healthy()

        # Filter out unnecessary market trades
        market_trades = [
            trade
            for trade in market_trades
            if start_time <= trade.transaction_time <= end_time
        ]
        # Sort all market trades by timestamp
        market_trades.sort(key=lambda x: x.transaction_time)

        logging.info(
            f"Replaying {len(market_trades)} market trades "
            f"from {start_time} to {end_time}"
        )

        if len(market_trades) == 0:
            time_manager().reset(admin=self)
            return

        if (
            len(market_trades)
            != market_trades[-1].exchange_trade_id
            - market_trades[0].exchange_trade_id
            + 1
        ):
            logging.warning(
                f"Got {len(market_trades)} market trades "
                f"from trade id {market_trades[0].exchange_trade_id + 1} "
                f"to {market_trades[-1].exchange_trade_id}. "
                f"Some market trades might be missing!"
            )

        order_book = OrderBook(symbol)
        replay_events = [
            (trade.transaction_time, 1, trade.exchange_trade_id, trade)
            for trade in market_trades
        ] + [
            (record.exchange_time, 0, record.sequence, record)
            for record in book_updates
        ]
        replay_events.sort(key=lambda event: event[:3])

        for event_time, event_type, _, payload in replay_events:
            time_manager().use_fake_time(event_time, admin=self)
            if event_type == 0:
                update = payload.to_update()
                order_book.apply(update)
                self.events.order_book_update.send(
                    self.events.order_book_update, book_update=payload
                )
                self.events.order_book.send(
                    self.events.order_book, order_book=order_book
                )
            else:
                self.events.market_trade.send(
                    self.events.market_trade, market_trade=payload
                )
                logging.debug("Received Market Trade: %s", payload)
        time_manager().reset(admin=self)
