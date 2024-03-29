from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.candlestick_list import CandlestickList
from jolteon.strategy.core.patterns.bull_flag.parameters import (
    BullFlagParameters,
)
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)


class BullFlagRecognizer(Heartbeater, SignalSubscriber):
    def __init__(self, params: BullFlagParameters):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.bull_flag_signal = signal("bull_flag")
        self._params = params
        self._all_candlesticks = CandlestickList(
            max_length=params.max_number_of_recent_candlesticks
        )

    def on_candlesticks(self, sender: str, candlesticks: list[Candlestick]):
        for candlestick in candlesticks:
            self.on_candlestick(sender, candlestick)

    @subscribe("calculated_candlestick_feed")
    def on_candlestick(self, _: str, candlestick: Candlestick):
        if (
            self._all_candlesticks.add_candlestick(candlestick)
            == CandlestickList.AddResult.APPENDED
        ):
            self._detect()

    def _detect(self):
        # Try search back N candlesticks and see if a bull flag pattern could
        # be found.
        completed_candlesticks = [
            c for c in self._all_candlesticks.candlesticks if c.is_completed()
        ]
        for i in range(0, len(completed_candlesticks)):
            index = len(completed_candlesticks) - 1 - i
            pattern = self._is_bull_flag_pattern(
                candlesticks=completed_candlesticks[index:]
            )
            # Only send valid bull flag pattern to gain some performance boost.
            if pattern and (
                self._params.verbose
                or pattern.result == RecognitionResult.BULL_FLAG
            ):
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
        # pattern length.
        # The shortest bull flag pattern at least has:
        # 1. A list of pre Bull-Flag candlesticks
        # 2. The Bull-Flag candlestick
        # 3. A list of post Bull-Flag consolidation candlesticks
        shortest_bull_flag_pattern_length = (
            self._params.max_number_of_pre_bull_flag_candlesticks + 2
        )

        if len(candlesticks) < shortest_bull_flag_pattern_length:
            return None

        # Divide the candlesticks into 3 periods
        previous_candlesticks = candlesticks[
            : self._params.max_number_of_pre_bull_flag_candlesticks
        ]
        bull_flag_candlestick = candlesticks[
            self._params.max_number_of_pre_bull_flag_candlesticks
        ]
        consolidation_candlesticks = candlesticks[
            self._params.max_number_of_pre_bull_flag_candlesticks + 1 :  # noqa
        ]

        if (
            len(consolidation_candlesticks)
            > self._params.max_number_of_consolidation_candlesticks
        ):
            return None

        pattern = BullFlagPattern(
            bull_flag_candlestick=bull_flag_candlestick,
            consolidation_period_candlesticks=consolidation_candlesticks,
        )

        # Check if the first candlestick is extremely bullish
        starts_extremely_bullish = True
        for previous_candlestick in previous_candlesticks:
            if not self._is_extremely_bullish(
                current=bull_flag_candlestick,
                previous=previous_candlestick,
            ):
                starts_extremely_bullish = False
                break

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
