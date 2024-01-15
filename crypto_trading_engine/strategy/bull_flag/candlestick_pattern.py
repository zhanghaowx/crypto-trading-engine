import logging

from crypto_trading_engine.core.time.time_manager import time_manager
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


class CandlestickPattern:
    def __init__(self, params: Parameters):
        self.params = params

    """
    Recognize candlestick patterns useful to bull flag strategy.
    """

    def is_bull_flag(
        self, candlesticks: list[Candlestick]
    ) -> TradeOpportunity:
        if len(candlesticks) <= 4:
            return TradeOpportunity()

        previous_candlestick = candlesticks[0]
        bull_flag_candlestick = candlesticks[1]
        consolidation_period_candlesticks = candlesticks[2:]

        # Check if the first candlestick is extremely bullish
        if self._is_extremely_bullish(
            current=bull_flag_candlestick,
            previous=previous_candlestick,
        ):
            if self._has_consolidation_period(
                bull_flag_candlestick=bull_flag_candlestick,
                following_candlesticks=consolidation_period_candlesticks,
            ):
                stop_loss1 = self._find_stop_loss_in_consolidation_period(
                    consolidation_period_candlesticks
                )
                atr = self._calculate_last_candlestick_atr(
                    candlesticks, len(candlesticks)
                )
                market_price = candlesticks[-1].close
                factor = 1.0  # The factor by which to check down movement.
                stop_loss2 = market_price - factor * atr

                logging.info(
                    f"Time: {time_manager().now()}, "
                    f"Stop loss: ({stop_loss1}, {stop_loss2}), "
                    f"Bull Flag: {bull_flag_candlestick}"
                )

                if stop_loss1 and stop_loss2:
                    stop_loss = min(stop_loss1, stop_loss2)
                    profit_price = (
                        bull_flag_candlestick.close - stop_loss
                    ) * 2.0 + bull_flag_candlestick.close
                    return TradeOpportunity(
                        stop_loss_price=min(stop_loss1, stop_loss2),
                        profit_price=profit_price,
                        score=1.0,
                    )

        return TradeOpportunity()

    def _has_consolidation_period(
        self,
        bull_flag_candlestick: Candlestick,
        following_candlesticks: list[Candlestick],
    ) -> bool:
        assert len(following_candlesticks) > 0

        for candlestick in following_candlesticks:
            bull_flag_body = abs(
                bull_flag_candlestick.open - bull_flag_candlestick.close
            )
            max_current_body = (
                bull_flag_body * self.params.consolidation_period_threshold
            )
            current_body = abs(candlestick.open - candlestick.close)

            if current_body > max_current_body:
                return False

        return True

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
    def _find_stop_loss_in_consolidation_period(
        consolidation_candlesticks: list[Candlestick],
    ) -> float | None:
        # Find the index of the candlestick with the lowest price
        lowest_price_index = consolidation_candlesticks.index(
            min(consolidation_candlesticks, key=lambda x: x.close)
        )

        # Check if the lowest price is the last candlestick in the
        # consolidation period
        if lowest_price_index == len(consolidation_candlesticks) - 1:
            return None
        else:
            return consolidation_candlesticks[lowest_price_index].close
