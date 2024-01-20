import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Union

from coinbase.rest import RESTClient

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick_generator import CandlestickGenerator
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class HistoricalFeed(Heartbeater):
    CACHE = dict[tuple, list[Trade]]()

    def __init__(
        self,
        candlestick_interval_in_seconds: int = 60,
        replay_speed: int = 600,
        api_key: Union[str, None] = None,
        api_secret: Union[str, None] = None,
    ):
        """
        Creates a historical market data feed client for the given time frame.

        Args:
            candlestick_interval_in_seconds: Granularity of the candlesticks in
                                             seconds.
            replay_speed: Speed at which to replay candlesticks. 60 means
                          real time and replay time ratio is 1:60. Every
                          second the replay time will advance 60 seconds.
            api_key: API key for Coinbase's REST API.
            api_secret: API secret for Coinbase's REST API.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.events = Events()
        self._replay_speed = replay_speed
        self._candlestick_generator = CandlestickGenerator(
            interval_in_seconds=candlestick_interval_in_seconds
        )
        self._client = RESTClient(
            api_key=(api_key if api_key else os.getenv("COINBASE_API_KEY")),
            api_secret=(
                api_secret if api_secret else os.getenv("COINBASE_API_SECRET")
            ),
        )
        time_manager().claim_admin(self)

    async def connect(
        self,
        symbol: str,
        start_time: datetime = time_manager().now() - timedelta(minutes=1),
        end_time: datetime = time_manager().now(),
    ):
        """
        Download the historical market data feed for the given symbol and
        time frame. Replay the candlesticks at the specified replay speed.
        Args:
            symbol: Symbol of the product to download historical market data
            start_time: Start time of the historical market data feed.
            end_time: End time of the historical market data feed
        Returns:
            A asyncio task to be waiting for incoming messages
        """

        def _generate_time_ranges(interval_minutes: int = 1):
            """
            Coinbase REST API has some limitations on how much you could
            request for each request.
            """
            result_time_ranges = []

            current_time = start_time
            while (end_time - current_time).total_seconds() > 1:
                next_time = current_time + timedelta(minutes=interval_minutes)
                result_time_ranges.append((current_time, next_time))
                current_time = next_time

            return result_time_ranges

        interval_minutes = 5
        for period_start, period_end in _generate_time_ranges(
            interval_minutes=interval_minutes
        ):
            market_trades = self._get_market_trades(
                symbol, period_start, period_end, limit=1000
            )
            market_trades.sort(key=lambda x: x.transaction_time)

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

                await asyncio.sleep(interval_minutes * 60 / self._replay_speed)

    # noinspection PyArgumentList
    def _get_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime, limit: int
    ) -> list[Trade]:
        key = (symbol, start_time, end_time)
        if self.CACHE.get(key) is not None:
            return self.CACHE[key]

        # Get snapshot information, by product ID, about the last trades
        # (ticks), best bid/ask, and 24h volume.
        json_response = self._client.get_market_trades(
            product_id=symbol,
            start=int(start_time.timestamp()),
            end=int(end_time.timestamp()),
            limit=limit,
        )
        assert len(json_response["trades"]) > 0

        market_trades = list[Trade]()
        for trade_json in json_response["trades"]:
            try:
                trade = Trade(
                    trade_id=id_generator().next(),
                    symbol=trade_json["product_id"],
                    client_order_id="",
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide.parse(trade_json["side"]),
                    price=float(trade_json["price"]),
                    quantity=float(trade_json["size"]),
                    transaction_time=datetime.fromisoformat(
                        trade_json["time"]
                    ),
                )
                market_trades.append(trade)
            except Exception as e:
                logging.error(
                    f"Could not parse market trade '{trade_json}': {e}"
                )
                continue  # Try next trade in the JSON response

        # Save in the cache to reduce calls to Coinbase API
        self.CACHE[key] = market_trades
        return market_trades
