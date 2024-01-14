import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Union

import pytz
from blinker import signal
from coinbase.rest import RESTClient

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.time.time_manager import create_time_manager
from crypto_trading_engine.market_data.core.candlestick import Candlestick


class HistoricalFeed(Heartbeater):
    """
    Access the historical market data feed using Coinbase's REST API.
    """

    @dataclass
    class Events:
        """
        Summary of all supported events for Coinbase's websocket channels,
        as well as events calculated from Coinbase's native events.

        See Also:
            https://docs.cloud.coinbase.com/exchange/docs/websocket-channels
        """

        candlestick = signal("calculated_candlestick_feed")

    class CandlestickGranularity(Enum):
        ONE_MINUTE = 60
        FIVE_MINUTE = 300
        FIFTEEN_MINUTE = 900
        THIRTY_MINUTE = 1800
        ONE_HOUR = 3600
        TWO_HOUR = 7200
        SIX_HOUR = 14400
        ONE_DAY = 86400

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
        super().__init__(type(self).__name__, interval_in_seconds=0)
        self.events = HistoricalFeed.Events()
        self._candlestick_granularity = HistoricalFeed.CandlestickGranularity(
            candlestick_interval_in_seconds
        )
        self._replay_speed = replay_speed
        self._client = RESTClient(
            api_key=(api_key if api_key else os.getenv("COINBASE_API_KEY")),
            api_secret=(
                api_secret if api_secret else os.getenv("COINBASE_API_SECRET")
            ),
        )
        self.time_manager = create_time_manager()
        self.time_manager.claim_admin(self)

    async def connect(
        self,
        symbol: str,
        start_time: datetime = datetime.now(pytz.utc) - timedelta(minutes=300),
        end_time: datetime = datetime.now(pytz.utc),
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
        candlesticks = self._get_candlesticks(symbol, start_time, end_time)
        candlesticks.sort(key=lambda x: x.start_time)

        for candlestick in candlesticks:
            self.time_manager.use_fake_time(candlestick.end_time, admin=self)
            self.events.candlestick.send(
                self.events.candlestick, candlestick=candlestick
            )
            await asyncio.sleep(
                self._candlestick_granularity.value / self._replay_speed
            )

    # noinspection PyArgumentList
    def _get_candlesticks(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[Candlestick]:
        json_response = self._client.get_candles(
            product_id=symbol,
            start=int(start_time.timestamp()),
            end=int(end_time.timestamp()),
            granularity=self._candlestick_granularity.name,
        )
        assert len(json_response["candles"]) > 0

        candlesticks = list[Candlestick]()
        for json in json_response["candles"]:
            candlestick = Candlestick(
                datetime.fromtimestamp(int(json["start"]), tz=pytz.utc),
                duration_in_seconds=self._candlestick_granularity.value,
            )
            candlestick.open = float(json["open"])
            candlestick.high = float(json["high"])
            candlestick.low = float(json["low"])
            candlestick.close = float(json["close"])
            candlestick.volume = float(json["volume"])

            candlesticks.append(candlestick)

        return candlesticks
