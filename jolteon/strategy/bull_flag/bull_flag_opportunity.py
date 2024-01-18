from dataclasses import dataclass

from jolteon.strategy.bull_flag.parameters import Parameters
from jolteon.strategy.core.patterns.bull_flag.pattern import BullFlagPattern
from jolteon.strategy.core.trade_opportunity import TradeOpportunity


@dataclass
class BullFlagOpportunity(TradeOpportunity):
    bull_flag_pattern: BullFlagPattern
    expected_trade_price: float = 0.0
    stop_loss_from_atr: float = 0.0
    stop_loss_from_support: float = 0.0
    risk_reward_ratio: float = 0.0

    def __init__(
        self,
        pattern: BullFlagPattern,
        target_reward_risk_ratio: float,
        atr: float,
    ):
        super().__init__(
            score=0.0,
            stop_loss_price=0.0,
            profit_price=0.0,
        )
        self.bull_flag_pattern = pattern
        self.expected_trade_price = pattern.consolidation[-1].close

        atr_factor = 1.1  # The factor by which to check down movement.
        self.stop_loss_from_atr = self.expected_trade_price - atr * atr_factor
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
        self.risk_reward_ratio = (
            self.profit_price - self.expected_trade_price
        ) / (self.expected_trade_price - self.stop_loss_price)

    def grade(self, params: Parameters) -> None:
        """
        Based on all characteristics of the opportunity, assign a grade to the
        trade opportunity.

        Args:
            params: Parameters for bull flag strategy.
        Returns:
            None
        """
        assert self.bull_flag_pattern.consolidation_max_ratio > 0.0
        self.score = 1.0 - max(
            0.0,
            (
                self.bull_flag_pattern.consolidation_max_ratio
                - params.consolidation_period_threshold
            )
            / params.consolidation_period_threshold,
        )