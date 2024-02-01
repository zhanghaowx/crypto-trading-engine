import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.data_source import IDataSource


class HistoricalFeed(Heartbeater):
    @dataclass
    class ErrorCode(StrEnum):
        DOWNLOADING = auto()

    """
    Download and replay the historical market data feed.
    """

    def __init__(
        self,
        data_source: IDataSource,
        candlestick_interval_in_seconds: int = 60,
    ):
        """
        Creates a historical market data feed client for the given time frame.

        Args:
            candlestick_interval_in_seconds: Granularity of the candlesticks in
                                             seconds.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = Events()
        self._data_source = data_source
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )
        time_manager().claim_admin(self)

    async def connect(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ):
        """
        Download the historical market data feed for the given symbol and
        time frame. Replay the candlesticks at the specified replay speed.
        Args:
            symbol: Symbol of the product to download historical market data
            start_time: Start time of the historical market data feed.
            end_time: End time of the historical market data feed.
        Returns:
            A asyncio task to be waiting for incoming messages
        """
        time_manager().use_fake_time(start_time, admin=self)

        self.add_issue(
            HeartbeatLevel.WARN, HistoricalFeed.ErrorCode.DOWNLOADING.name
        )
        market_trades = await self._data_source.download_market_trades(
            symbol, start_time, end_time
        )
        self.remove_issue(HistoricalFeed.ErrorCode.DOWNLOADING.name)

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
            return

        if (
            len(market_trades)
            != market_trades[-1].trade_id - market_trades[0].trade_id + 1
        ):
            logging.warning(
                f"Got {len(market_trades)} market trades "
                f"from trade id {market_trades[0].trade_id + 1} "
                f"to {market_trades[-1].trade_id}. "
                f"Some market trades might be missing!"
            )

        for market_trade in market_trades:
            time_manager().use_fake_time(
                market_trade.transaction_time, admin=self
            )
            self.events.market_trade.send(
                self.events.market_trade, market_trade=market_trade
            )
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
