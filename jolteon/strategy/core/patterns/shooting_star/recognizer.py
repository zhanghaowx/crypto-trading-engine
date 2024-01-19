from blinker import signal

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.candlestick_list import CandlestickList
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)
from jolteon.strategy.core.patterns.shooting_star.pattern import (
    ShootingStarPattern,
)


class ShootingStarRecognizer(Heartbeater):
    def __init__(self, params: ShootingStarParameters):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.shooting_star_signal = signal("shooting_star")
        self._params = params
        self._all_candlesticks = CandlestickList(
            max_length=params.max_number_of_recent_candlesticks
        )
        assert len(self._all_candlesticks.candlesticks) == 0

    def on_candlestick(self, sender: str, candlestick: Candlestick):
        self._all_candlesticks.add_candlestick(candlestick)
        self._detect()

    def _detect(self):
        """
        A shooting star is a specific candlestick pattern in technical analysis
        that is generally considered a bearish reversal pattern.
        It typically occurs during an uptrend and has the following
        characteristics:

        1. The candlestick has a small real body
           (the difference between open and close prices).
        2. There is a long upper shadow (wick) that is at least twice the
           length of the real body.
        3. The lower shadow (wick) is very small or nonexistent.

        +---------|--------+
        |         |        |
        |         |        |
        |         |        |
        |         |        |
        |         |        |
        |         |        |
        |     Wick|        |
        |Close+---|--+     |
        |     | Body |     |
        |Open +---|--+     |
        |     Wick|        |
        +---------|--------+

        Returns:

        """
        candlestick = self._all_candlesticks.candlesticks[-1]

        body_ratio = abs(candlestick.open - candlestick.close) / (
            max(0.01, candlestick.high - candlestick.low)
        )

        upper_shadow_ratio = (
            candlestick.high - max(candlestick.open, candlestick.close)
        ) / max(0.01, abs(candlestick.open - candlestick.close))

        lower_shadow_ratio = (
            min(candlestick.open, candlestick.close) - candlestick.low
        ) / max(0.01, candlestick.high - candlestick.low)

        if (
            body_ratio < self._params.max_body_ratio
            and upper_shadow_ratio >= self._params.min_upper_shadow_ratio
            and lower_shadow_ratio < self._params.max_lower_shadow_ratio
        ):
            self.shooting_star_signal.send(
                self.shooting_star_signal,
                pattern=ShootingStarPattern(
                    shooting_star=candlestick,
                    body_ratio=body_ratio,
                    upper_shadow_ratio=upper_shadow_ratio,
                    lower_shadow_ratio=lower_shadow_ratio,
                ),
            )
