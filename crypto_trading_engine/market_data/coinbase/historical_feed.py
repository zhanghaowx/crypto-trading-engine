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
        FIVE_MINUTES = 300
        FIFTEEN_MINUTES = 900
        THIRTY_MINUTES = 1800
        ONE_HOUR = 3600
        TWO_HOURS = 7200
        SIX_HOURS = 14400
        ONE_DAY = 86400

    def __init__(
        self,
        start_time: datetime = datetime.now(pytz.utc) - timedelta(minutes=300),
        end_time: datetime = datetime.now(pytz.utc),
        candlestick_interval_in_seconds: int = 60,
        replay_speed: int = 600,
        api_key: Union[str, None] = None,
        api_secret: Union[str, None] = None,
    ):
        super().__init__(type(self).__name__, interval_in_seconds=0)
        self.events = HistoricalFeed.Events()
        self._start_time = start_time
        self._end_time = end_time
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

    async def connect(self, symbol: str):
        candlesticks = self._get_candlesticks(symbol)
        candlesticks.sort(key=lambda x: x.start_time)

        for candlestick in candlesticks:
            self.events.candlestick.send(
                self.events.candlestick, candlestick=candlestick
            )
            await asyncio.sleep(
                self._candlestick_granularity.value / self._replay_speed
            )

    # noinspection PyArgumentList
    def _get_candlesticks(self, symbol: str) -> list[Candlestick]:
        json_response = self._client.get_candles(
            product_id=symbol,
            start=int(self._start_time.timestamp()),
            end=int(self._end_time.timestamp()),
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
