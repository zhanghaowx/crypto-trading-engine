from dataclasses import dataclass
from typing import Union

from jolteon.market_data.core.candlestick_list import CandlestickList
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
from jolteon.strategy.core.patterns.bull_flag.pattern import BullFlagPattern
from jolteon.strategy.core.trade_opportunity import TradeOpportunityCore


@dataclass
class TradeOpportunity(TradeOpportunityCore):
    bull_flag_pattern: BullFlagPattern
    expected_trade_price: float = 0.0
    stop_loss_from_atr: float = 0.0
    stop_loss_from_support: float = 0.0
    score_details: Union[dict, None] = None

    def __init__(
        self,
        pattern: BullFlagPattern,
        target_reward_risk_ratio: float,
        adjusted_atr: float,
    ):
        super().__init__(
            score=0.0,
            stop_loss_price=0.0,
            profit_price=0.0,
        )
        self.bull_flag_pattern = pattern
        self.expected_trade_price = pattern.consolidation[-1].close

        self.stop_loss_from_atr = self.expected_trade_price - adjusted_atr
        self.stop_loss_from_support = min(
            [x.low for x in pattern.consolidation]
        )

        self.stop_loss_price = max(
            min(self.stop_loss_from_atr, self.stop_loss_from_support),
            pattern.bull_flag.open,
        )

        self.profit_price = (
            self.expected_trade_price - self.stop_loss_price
        ) * target_reward_risk_ratio + self.expected_trade_price

    def grade(
        self, history: CandlestickList, params: StrategyParameters
    ) -> None:
        """
        Based on all characteristics of the opportunity, assign a grade to the
        trade opportunity.

        Args:
            history: All current/previous candlesticks for this opportunity
            params: Parameters for bull flag strategy.
        Returns:
            None
        """
        previous_candlesticks = [
            candlestick
            for candlestick in history.candlesticks
            if candlestick.end_time
            <= self.bull_flag_pattern.bull_flag.start_time
        ]

        #######################
        # Build Score Details #
        #######################
        self.score_details = {
            "n_prev_candlesticks": len(previous_candlesticks)
        }

        # The percentage of bullish candlesticks in history
        is_bullish = [
            candlestick.is_bullish() for candlestick in previous_candlesticks
        ]
        prev_bullish_pct = sum(is_bullish) / max(1e-10, len(is_bullish))
        self.score_details["prev_bullish_pct"] = prev_bullish_pct

        # Min/Max return percentage of candlesticks in history
        return_percentages = [
            candlestick.return_percentage()
            for candlestick in previous_candlesticks
        ]
        if len(return_percentages) == 0:
            self.score_details["min_prev_return_pct"] = 0
            self.score_details["max_prev_return_pct"] = 0
        else:
            self.score_details["min_prev_return_pct"] = min(return_percentages)
            self.score_details["max_prev_return_pct"] = max(return_percentages)
        self.score_details[
            "bull_flag_return_pct"
        ] = self.bull_flag_pattern.bull_flag.return_percentage()

        ###############
        # Build Score #
        ###############
        self.score = 0.0

        # Before the "bull flag", we hope the previous trend is a bearish trend
        # so that we are not following a bullish trend at a late point

        self.score += 0.25 * (1 - self.score_details["prev_bullish_pct"])
        self.score += 0.25 * (
            1
            - max(
                abs(self.score_details["max_prev_return_pct"]),
                abs(self.score_details["min_prev_return_pct"]),
            )
            / self.score_details["bull_flag_return_pct"]
        )
        self.score += 0.5 * (
            self.score_details["n_prev_candlesticks"]
            / params.max_number_of_recent_candlesticks
        )
