from dataclasses import dataclass


@dataclass(frozen=True)
class Parameters:
    """
    Parameters of the bull flag strategy.
    """

    # Maximum number of candlesticks to keep in the history
    max_number_of_recent_candlesticks: int = 10
    # A candlestick's body needs to be larger than `threshold * body of its
    # previous candlestick` in order to be considered as an extremely bullish
    # candlestick and potentially marked as the starting of a bull flag.
    extreme_bullish_threshold: float = 2.0
    # A candlestick's return percentage needs to be larger than X in order to
    # be considered as an extremely bullish candlestick and potentially marked
    # as the starting of a bull flag
    extreme_bullish_return_pct: float = 0.001
    # A candlestick is suggested to be smaller than `threshold * body of
    # previous extremely bullish candlestick` in order to be considered as part
    # of the consolidation period. Exceeding this threshold will lower its
    # score
    consolidation_period_threshold: float = 0.2
    # A candlestick needs to be smaller than `threshold * body of previous
    # extremely bullish candlestick` in order to be considered as part of
    # the consolidation period.
    consolidation_period_threshold_cutoff: float = 0.4
    # Reward:Risk needs to be higher than X. The default value is 2.0. This
    # requires our strategy to have a win rate of 33.33% or higher.
    target_reward_risk_ratio: float = 2.0
    # When an opportunity score is below the cutoff, it will not be considered
    opportunity_score_cutoff: float = 0.5
