import math

from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.bull_flag_opportunity import (
    BullFlagOpportunity,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


class BullFlagPattern:
    def __init__(self, params: Parameters):
        self.params = params

    """
    Recognize candlestick patterns useful to bull flag strategy. A bull flag
    pattern consists at least three candlesticks:
     * A first small candlestick to set the baseline
     * An extremely bullish candlestick when compared with the 1st candlestick
     * Followed by a consolidation period which could be as short as 1
       candlestick.
    """

    def is_bull_flag(
        self, candlesticks: list[Candlestick]
    ) -> BullFlagOpportunity | None:
        assert len(candlesticks) > 0

        # Check if number of candlesticks is less than the shortest bull flag
        # pattern length
        shortest_bull_flag_length = 3
        if len(candlesticks) <= shortest_bull_flag_length:
            return None

        # Divide the candlesticks into 3 periods
        previous_candlestick = candlesticks[0]
        bull_flag_candlestick = candlesticks[1]
        consolidation_period_candlesticks = candlesticks[2:]

        opportunity = BullFlagOpportunity(
            start=bull_flag_candlestick.start_time,
            end=consolidation_period_candlesticks[-1].start_time,
        )
        opportunity.set_bull_flag(bull_flag_candlestick)
        opportunity.set_consolidation(consolidation_period_candlesticks)

        # Check if the first candlestick is extremely bullish
        opportunity.starts_extremely_bullish = self._is_extremely_bullish(
            current=bull_flag_candlestick,
            previous=previous_candlestick,
        )
        if not opportunity.starts_extremely_bullish:
            return opportunity

        # Check if there is a consolidation period
        if (
            opportunity.consolidation_period_max_ratio
            > self.params.consolidation_period_threshold_cutoff
        ):
            return opportunity

        opportunity.stop_loss_from_support = self._calculate_lowest_price(
            consolidation_period_candlesticks
        )

        # If the last candlestick is bearish and there is no other support
        # line (lower than last close price) in the consolidation period,
        # we will give up.
        if math.isclose(
            opportunity.expected_trade_price,
            opportunity.stop_loss_from_support,
        ):
            return opportunity

        atr = self._calculate_last_candlestick_atr(
            candlesticks, len(candlesticks)
        )
        factor = 1.0  # The factor by which to check down movement.

        opportunity.stop_loss_from_atr = (
            opportunity.expected_trade_price - factor * atr
        )

        opportunity.stop_loss_price = min(
            opportunity.stop_loss_from_atr, opportunity.stop_loss_from_support
        )

        opportunity.profit_price = (
            opportunity.expected_trade_price - opportunity.stop_loss_price
        ) * 2.0 + opportunity.expected_trade_price

        opportunity.risk_reward_ratio = (
            opportunity.profit_price - opportunity.expected_trade_price
        ) / (opportunity.expected_trade_price - opportunity.stop_loss_price)

        opportunity.grade(params=self.params)

        return opportunity

    def _is_extremely_bullish(
        self, current: Candlestick, previous: Candlestick
    ) -> bool:
        prev_body = abs(previous.open - previous.close)
        current_body = abs(current.open - current.close)

        cond1 = (
            current_body > prev_body * self.params.extreme_bullish_threshold
        )
        cond2 = (
            current.return_percentage()
            > self.params.extreme_bullish_return_pct
        )
        return cond1 and cond2

    @staticmethod
    def _calculate_last_candlestick_atr(
        candlesticks: list[Candlestick], period
    ):
        if len(candlesticks) < period:
            raise ValueError("Insufficient data to calculate ATR")

        true_ranges = []

        for i in range(len(candlesticks) - period, len(candlesticks)):
            high_low = candlesticks[i].high - candlesticks[i].low
            high_close = abs(candlesticks[i].high - candlesticks[i - 1].close)
            low_close = abs(candlesticks[i].low - candlesticks[i - 1].close)
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)

        atr = sum(true_ranges) / period

        return atr

    @staticmethod
    def _calculate_lowest_price(
        consolidation_period: list[Candlestick],
    ) -> float:
        assert len(consolidation_period) > 0

        lowest_close_price = min([x.close for x in consolidation_period])
        lowest_open_price = min([x.open for x in consolidation_period])

        return min(lowest_close_price, lowest_open_price)
