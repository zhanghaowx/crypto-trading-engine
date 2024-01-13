from crypto_trading_engine.core.time.time_manager import create_time_manager
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.bull_flag_opportunity import (
    BullFlagOpportunity,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


class CandlestickPattern:
    def __init__(self, params: Parameters):
        self.params = params

    """
    Recognize candlestick patterns useful to bull flag strategy.
    """

    def is_bull_flag(
        self, candlesticks: list[Candlestick]
    ) -> BullFlagOpportunity:
        if len(candlesticks) <= 4:
            return BullFlagOpportunity()

        previous_candlestick = candlesticks[0]
        bull_flag_candlestick = candlesticks[1]
        consolidation_period_candlesticks = candlesticks[2:]

        # Check if the first candlestick is extremely bullish
        if (
            bull_flag_candlestick.is_bullish()
            and self._is_extremely_bullish_or_bearish(
                current=bull_flag_candlestick,
                previous=previous_candlestick,
                threshold=self.params.extreme_bullish_threshold,
            )
        ):
            if self._has_consolidation_period(
                bull_flag_candlestick=bull_flag_candlestick,
                following_candlesticks=consolidation_period_candlesticks,
            ):
                stop_loss = self._find_stop_loss_in_consolidation_period(
                    consolidation_period_candlesticks
                )
                print(
                    f"Time: {create_time_manager().get_current_time()}, "
                    f"Stop loss: {stop_loss}, "
                    f"Bull Flag: {bull_flag_candlestick}, "
                    f"Consolidation: {consolidation_period_candlesticks}"
                )
                if stop_loss:
                    return BullFlagOpportunity(
                        stop_loss_price=stop_loss, score=1.0
                    )

        return BullFlagOpportunity()

    def _has_consolidation_period(
        self,
        bull_flag_candlestick: Candlestick,
        following_candlesticks: list[Candlestick],
    ) -> bool:
        assert len(following_candlesticks) > 0
        for candlestick in following_candlesticks:
            if CandlestickPattern._is_extremely_bullish_or_bearish(
                current=candlestick,
                previous=bull_flag_candlestick,
                threshold=self.params.consolidation_period_threshold,
            ):
                return False

        return True

    @staticmethod
    def _is_extremely_bullish_or_bearish(
        current: Candlestick, previous: Candlestick, threshold: float
    ) -> bool:
        prev_body = abs(previous.open - previous.close)
        current_body = abs(current.open - current.close)
        return current_body > prev_body * threshold

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
