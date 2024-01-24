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
        self.score = 1.0
        self.score_details = {}

        previous_candlesticks = [
            candlestick
            for candlestick in history.candlesticks
            if candlestick.end_time
            <= self.bull_flag_pattern.bull_flag.start_time
        ]

        # The percentage of bullish candlesticks in history
        is_bullish = [
            candlestick.is_bullish() for candlestick in previous_candlesticks
        ]
        is_bullish_pct = sum(is_bullish) / max(1e-10, len(is_bullish))
        self.score_details["is_bullish_pct"] = is_bullish_pct
        if self.score_details["is_bullish_pct"] <= 0.5:
            self.score -= 0.5
