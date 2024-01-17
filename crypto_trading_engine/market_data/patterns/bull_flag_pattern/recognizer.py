from collections import deque

from blinker import signal

from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.patterns.bull_flag_pattern.pattern import (
    Pattern,
    RecognitionResult,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


class Recognizer:
    def __init__(self, params: Parameters):
        self.bull_flag_signal = signal("bull_flag_pattern")
        self._params = params
        self._all_candlesticks = deque[Candlestick](
            maxlen=params.max_number_of_recent_candlesticks
        )

    def on_candlesticks(self, sender: str, candlesticks: list[Candlestick]):
        for candlestick in candlesticks:
            self.on_candlestick(sender, candlestick)

    def on_candlestick(self, sender: str, candlestick: Candlestick):
        # Merge candlesticks
        assert (
            len(self._all_candlesticks) == 0
            or self._all_candlesticks[-1].start_time <= candlestick.start_time
        ), (
            "Candlesticks shall be sent in time order! "
            f"Last candlestick in history: "
            f"{self._all_candlesticks[-1].start_time}, "
            f"current candlestick: {candlestick.start_time}"
        )

        if (
            len(self._all_candlesticks) == 0
            or self._all_candlesticks[-1].start_time < candlestick.start_time
        ):
            self._all_candlesticks.append(candlestick)
        else:
            assert (
                self._all_candlesticks[-1].start_time == candlestick.start_time
            ), "Candlesticks shall be stored in time order!"
            self._all_candlesticks[-1] = candlestick

        self._detect()

    def _detect(self):
        # Try search back N candlesticks and see if a bull flag pattern could
        # be found.
        for i in range(0, len(self._all_candlesticks)):
            index = len(self._all_candlesticks) - 1 - i
            pattern = self._is_bull_flag_pattern(
                candlesticks=list(self._all_candlesticks)[index:]
            )
            if pattern:
                self.bull_flag_signal.send(
                    self.bull_flag_signal, pattern=pattern
                )

        return

    def _is_bull_flag_pattern(
        self, candlesticks: list[Candlestick]
    ) -> Pattern | None:
        """
        Whether it forms a bull flag pattern.
        Args:
            candlesticks: A list of candlesticks in the past.
        Returns:
            A Pattern object on why we think it is a bull flag pattern.
        """
        assert len(candlesticks) > 0

        # Check if number of candlesticks is less than the shortest bull flag
        # pattern length
        shortest_bull_flag_pattern_length = 3
        if len(candlesticks) < shortest_bull_flag_pattern_length:
            return None

        # Divide the candlesticks into 3 periods
        previous_candlestick = candlesticks[0]
        bull_flag_candlestick = candlesticks[1]

        pattern = Pattern(
            bull_flag_candlestick=bull_flag_candlestick,
            consolidation_period_candlesticks=candlesticks[2:],
        )

        # Check if the first candlestick is extremely bullish
        starts_extremely_bullish = self._is_extremely_bullish(
            current=bull_flag_candlestick,
            previous=previous_candlestick,
        )
        if not starts_extremely_bullish:
            pattern.result = RecognitionResult.NO_EXTREME_BULLISH
            return pattern

        # Check if there is a consolidation period
        if (
            pattern.consolidation_max_ratio
            > self._params.consolidation_period_threshold_cutoff
        ):
            pattern.result = RecognitionResult.NO_CONSOLIDATION_PERIOD
            return pattern

        pattern.result = RecognitionResult.BULL_FLAG
        return pattern

    def _is_extremely_bullish(
        self, current: Candlestick, previous: Candlestick
    ) -> bool:
        prev_body = abs(previous.open - previous.close)
        current_body = abs(current.open - current.close)

        cond1 = (
            current_body > prev_body * self._params.extreme_bullish_threshold
        )
        cond2 = (
            current.return_percentage()
            > self._params.extreme_bullish_return_pct
        )
        return cond1 and cond2
