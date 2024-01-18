from blinker import signal

from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.candlestick_list import CandlestickList
from jolteon.strategy.bull_flag.parameters import Parameters
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)


class BullFlagRecognizer:
    def __init__(self, params: Parameters):
        self.bull_flag_signal = signal("bull_flag")
        self._params = params
        self._all_candlesticks = CandlestickList(
            max_length=params.max_number_of_recent_candlesticks
        )

    def on_candlesticks(self, sender: str, candlesticks: list[Candlestick]):
        for candlestick in candlesticks:
            self.on_candlestick(sender, candlestick)

    def on_candlestick(self, sender: str, candlestick: Candlestick):
        self._all_candlesticks.add_candlestick(candlestick)
        self._detect()

    def _detect(self):
        # Try search back N candlesticks and see if a bull flag pattern could
        # be found.
        for i in range(0, len(self._all_candlesticks.candlesticks)):
            index = len(self._all_candlesticks.candlesticks) - 1 - i
            pattern = self._is_bull_flag_pattern(
                candlesticks=list(self._all_candlesticks.candlesticks)[index:]
            )
            if pattern:
                self.bull_flag_signal.send(
                    self.bull_flag_signal, pattern=pattern
                )

        return

    def _is_bull_flag_pattern(
        self, candlesticks: list[Candlestick]
    ) -> BullFlagPattern | None:
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

        pattern = BullFlagPattern(
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
