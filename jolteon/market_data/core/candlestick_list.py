from collections import deque

from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.algorithms import calculate_atr


class CandlestickList:
    def __init__(self, max_length: int):
        self.candlesticks = deque[Candlestick](
            maxlen=max_length,
        )

    def add_candlestick(self, candlestick: Candlestick):
        # It shall be either an update on last candlestick or a new
        # candlestick.

        # Merge candlesticks
        assert (
            len(self.candlesticks) == 0
            or self.candlesticks[-1].start_time <= candlestick.start_time
        ), (
            "Candlesticks shall be sent in time order! "
            f"Last candlestick in history: "
            f"{self.candlesticks[-1].start_time}, "
            f"current candlestick: {candlestick.start_time}"
        )

        if (
            len(self.candlesticks) == 0
            or self.candlesticks[-1].start_time < candlestick.start_time
        ):
            self.candlesticks.append(candlestick)
        else:
            assert self.candlesticks[-1].start_time == candlestick.start_time
            self.candlesticks[-1] = candlestick

    def atr(self, period: int = -1) -> float:
        if period < 0:
            period = len(self.candlesticks)
        return calculate_atr(list(self.candlesticks), period)
