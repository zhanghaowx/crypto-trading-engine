from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Union

from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.candlestick_list import CandlestickList


@dataclass
class RSI:
    timestamp: datetime
    period: int
    rsi: float
    average_gain: float
    average_loss: float


class RSICalculator(SignalSubscriber):
    """
    RSICalculator is a class for calculating the Relative Strength Index (RSI)
    from a stream of candlestick data.

    RSI is a momentum indicator used in technical analysis. RSI measures the
    speed and magnitude of a security's recent price changes to evaluate
    overvalued or undervalued conditions in the price of that security.
    """

    def __init__(self, period: int = 14):
        self._period: int = period
        self._candlesticks = CandlestickList(max_length=period + 2)
        self._gains = deque[float](maxlen=period)
        self._losses = deque[float](maxlen=period)
        self._previous_rsi: Union[RSI, None] = None
        self.rsi_event = signal("rsi")

    @subscribe("calculated_candlestick_feed")
    def on_candlestick(self, _: str, candlestick: Candlestick):
        """
        Calculate RSI on receiving a new candlestick.

        Args:
            _: Unused argument
            candlestick: A new candlestick

        Returns:
            None
        """
        added = self._candlesticks.add_candlestick(candlestick=candlestick)
        if added == CandlestickList.AddResult.MERGED:
            return

        # Exclude the last candlestick which potentially could be incomplete

        if len(self._candlesticks) > 2:
            price_change = (
                self._candlesticks[-2].close - self._candlesticks[-3].close
            )
            if price_change > 0:
                self._gains.append(price_change)
                self._losses.append(0)
            else:
                self._gains.append(0)
                self._losses.append(abs(price_change))

        if not self._previous_rsi and self._candlesticks.is_full():
            rsi = self._calculate_rsi()
            self.rsi_event.send(self.rsi_event, rsi=rsi)
            self._previous_rsi = rsi
        elif self._previous_rsi:
            rsi = self._calculate_rsi_from(previous_rsi=self._previous_rsi)
            self.rsi_event.send(self.rsi_event, rsi=rsi)
            self._previous_rsi = rsi
        else:
            pass

    def _calculate_rsi(self) -> RSI:
        assert len(self._gains) == self._period, (
            f"RSICalculator has {len(self._gains)} gains, "
            f"expected to be {self._period}"
        )
        assert len(self._losses) == self._period, (
            f"RSICalculator has {len(self._losses)} losses, "
            f"expected to be {self._period}"
        )

        avg_gain = sum(self._gains) / self._period
        avg_loss = sum(self._losses) / self._period

        relative_strength = avg_gain / max(1e-10, avg_loss)
        rsi = 100 - (100 / (1 + relative_strength))

        assert 0 <= rsi <= 100, f"Unexpected RIS <{rsi}>"
        return RSI(
            timestamp=time_manager().now(),
            period=self._period,
            rsi=rsi,
            average_gain=avg_gain,
            average_loss=avg_loss,
        )

    def _calculate_rsi_from(self, previous_rsi: RSI) -> RSI:
        assert previous_rsi

        avg_gain = (
            previous_rsi.average_gain * (self._period - 1) + self._gains[-1]
        ) / self._period
        avg_loss = (
            previous_rsi.average_loss * (self._period - 1) + self._losses[-1]
        ) / self._period

        relative_strength = avg_gain / max(1e-10, avg_loss)
        rsi = 100 - (100 / (1 + relative_strength))

        assert 0 <= rsi <= 100, (
            f"Unexpected RIS <{rsi}>, " f"previous RIS: {previous_rsi}"
        )
        return RSI(
            timestamp=time_manager().now(),
            period=self._period,
            rsi=rsi,
            average_gain=avg_gain,
            average_loss=avg_loss,
        )
