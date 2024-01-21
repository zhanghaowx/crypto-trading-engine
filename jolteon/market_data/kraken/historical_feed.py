import asyncio
import logging
from datetime import datetime

import pytz
import requests

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class HistoricalFeed(Heartbeater):
    CACHE = dict[tuple, list[Trade]]()

    """
    Access the historical market data feed using Kraken's REST API.
    """

    def __init__(
        self,
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
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )
        time_manager().claim_admin(self)

    async def connect(
        self, symbol: str, start_time: datetime, end_time: datetime
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
        market_trades = self._get_market_trades(symbol, start_time, end_time)
        market_trades.sort(key=lambda x: x.transaction_time)

        logging.info(
            f"Replaying {len(market_trades)} market trades "
            f"from {start_time} to {end_time}"
        )

        for market_trade in market_trades:
            time_manager().use_fake_time(
                market_trade.transaction_time, admin=self
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

            # Add some delays between trades to
            await asyncio.sleep(0.01)

    # noinspection PyArgumentList
    def _get_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[Trade]:
        key = (symbol, start_time)
        if self.CACHE.get(key) is not None:
            return self.CACHE[key]

        market_trades = list[Trade]()
        request_timestamp = int(start_time.timestamp())

        while (
            len(market_trades) == 0
            or market_trades[-1].transaction_time < end_time
        ):
            # Start requesting REST API for data
            response = requests.get(
                f"https://api.kraken.com/0/public/Trades?"
                f"pair={symbol}&"
                f"since={request_timestamp}"
            )
            if response.status_code != 200:
                raise Exception(
                    f"Error getting historical market trades: "
                    f"HTTP {response.status_code}"
                )

            json_resp = response.json()
            if json_resp["error"] and len(json_resp["error"]) > 0:
                raise Exception(
                    f"Error getting historical market trades: "
                    f"{json_resp['error']}"
                )

            assert json_resp["result"] is not None
            json_trades = json_resp["result"][symbol]
            for json_trade in json_trades:
                # Array of trade entries
                # [
                #  <price>,
                #  <volume>,
                #  <time>,
                #  <buy/sell>,
                #  <market/limit>,
                #  <miscellaneous>,
                #  <trade_id>
                # ]
                trade = Trade(
                    trade_id=json_trade[6],
                    client_order_id="",
                    symbol=symbol,
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide.BUY
                    if json_trade[3] == "b"
                    else MarketSide.SELL,
                    price=float(json_trade[0]),
                    quantity=float(json_trade[1]),
                    transaction_time=datetime.fromtimestamp(
                        json_trade[2], tz=pytz.utc
                    ),
                )
                market_trades.append(trade)

            request_timestamp = json_resp["result"]["last"]

        # Save in the cache to reduce calls to Kraken's API
        self.CACHE[key] = market_trades
        return market_trades
