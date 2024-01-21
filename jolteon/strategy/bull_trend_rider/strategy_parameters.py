from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyParameters:
    """
    Parameters of the bull flag strategy.
    """

    # Maximum number of candlesticks to keep in the history
    max_number_of_recent_candlesticks: int = 10
    # A candlestick is suggested to be smaller than `threshold * body of
    # previous extremely bullish candlestick` in order to be considered as part
    # of the consolidation period. Exceeding this threshold will lower its
    # score
    consolidation_period_threshold: float = 0.2
    # Reward:Risk needs to be higher than X. The default value is 2.0. This
    # requires our strategy to have a win rate of 33.33% or higher.
    target_reward_risk_ratio: float = 2.0
    # When an opportunity score is below the cutoff, it will not be considered
    opportunity_score_cutoff: float = 0.5
    # Kraken/BTC
    min_quantity: float = 0.0001
