from collections import deque
from enum import Enum, auto

from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.algorithms import calculate_atr


class CandlestickList:
    class AddResult(Enum):
        APPENDED = auto()
        MERGED = auto()

    def __init__(self, max_length: int):
        self.candlesticks = deque[Candlestick](
            maxlen=max_length,
        )

    def __len__(self):
        return len(self.candlesticks)

    def __getitem__(self, index):
        return self.candlesticks[index]

    def is_full(self):
        return len(self.candlesticks) == self.candlesticks.maxlen

    def add_candlestick(self, candlestick: Candlestick):
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
            assert (
                len(self.candlesticks) == 0
                or self.candlesticks[-1].end_time == candlestick.start_time
            ), (
                f"Expects a continuous list of candlesticks without gaps, "
                f"last candlestick is {self.candlesticks[-1]}, "
                f" next candlestick is {candlestick}"
            )
            self.candlesticks.append(candlestick)
            return CandlestickList.AddResult.APPENDED
        else:
            assert self.candlesticks[-1].start_time == candlestick.start_time
            self.candlesticks[-1] = candlestick
            return CandlestickList.AddResult.MERGED

    def atr(self, period: int = -1) -> float:
        if period < 0:
            period = len(self.candlesticks)
        return calculate_atr(list(self.candlesticks), period)
