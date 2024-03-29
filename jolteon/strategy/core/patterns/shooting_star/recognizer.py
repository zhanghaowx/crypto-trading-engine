from typing import Union

from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.strategy.core.patterns.shooting_star.parameters import (
    ShootingStarParameters,
)
from jolteon.strategy.core.patterns.shooting_star.pattern import (
    ShootingStarPattern,
)


class ShootingStarRecognizer(Heartbeater, SignalSubscriber):
    def __init__(self, params: ShootingStarParameters):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.shooting_star_signal = signal("shooting_star")
        self._params = params
        self._last_candlestick: Union[Candlestick, None] = None

    @subscribe("calculated_candlestick_feed")
    def on_candlestick(self, sender: str, candlestick: Candlestick):
        # Check last candlestick
        if self._last_candlestick and self._last_candlestick.is_completed():
            self._detect_shooting_star(self._last_candlestick)
            # Once a candlestick is checked we no longer store it
            self._last_candlestick = None

        # Check current candlestick
        if candlestick.is_completed():
            # Once a candlestick is checked we no longer store it
            self._detect_shooting_star(candlestick)
        else:
            self._last_candlestick = candlestick

    def _detect_shooting_star(self, candlestick: Candlestick):
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
            0 < body_ratio < self._params.max_body_ratio
            and upper_shadow_ratio >= self._params.min_upper_shadow_ratio
            and 0 < lower_shadow_ratio < self._params.max_lower_shadow_ratio
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
            return True

        return False
