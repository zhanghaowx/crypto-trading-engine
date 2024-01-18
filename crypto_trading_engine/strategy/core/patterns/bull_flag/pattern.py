import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from crypto_trading_engine.market_data.core.candlestick import Candlestick


class RecognitionResult(StrEnum):
    UNKNOWN = "UNKNOWN"
    BULL_FLAG = "BULL_FLAG"
    NO_EXTREME_BULLISH = "NO_EXTREME_BULLISH"
    NO_CONSOLIDATION_PERIOD = "NO_CONSOLIDATION_PERIOD"


@dataclass
class BullFlagPattern:
    """
    Summary of the pattern recognized
    """

    start: datetime
    end: datetime
    bull_flag: Candlestick
    bull_flag_body: float
    consolidation: list[Candlestick]
    consolidation_max_ratio: float
    result: RecognitionResult = RecognitionResult.UNKNOWN

    def __init__(
        self,
        bull_flag_candlestick: Candlestick,
        consolidation_period_candlesticks: list[Candlestick],
    ):
        assert len(consolidation_period_candlesticks) > 0, (
            f"Cannot set consolidation period for {self} "
            f"because the provided consolidation period is empty!"
        )

        self.start = bull_flag_candlestick.start_time
        self.end = consolidation_period_candlesticks[-1].end_time

        self.bull_flag = bull_flag_candlestick
        self.bull_flag_body = (
            bull_flag_candlestick.close - bull_flag_candlestick.open
        )

        max_ratio = 0.0
        for candlestick in consolidation_period_candlesticks:
            current_body = abs(candlestick.open - candlestick.close)
            if abs(self.bull_flag_body) < 1e-10:
                if abs(current_body) < 1e-10:
                    max_ratio = 0.0
                else:
                    max_ratio = math.inf
            else:
                max_ratio = max(
                    max_ratio,
                    current_body / abs(self.bull_flag_body),
                )

        self.consolidation = consolidation_period_candlesticks
        self.consolidation_max_ratio = max_ratio
