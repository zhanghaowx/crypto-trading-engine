from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyParameters:
    """
    Parameters of the bull flag strategy.
    """

    # Maximum number of candlesticks to keep in the history
    max_number_of_recent_candlesticks: int = 10
    # Reward:Risk needs to be higher than X. The default value is 2.0. This
    # requires our strategy to have a win rate of 33.33% or higher.
    target_reward_risk_ratio: float = 2.0
    # When an opportunity score is below the cutoff, it will not be considered
    opportunity_score_cutoff: float = 0.0
    # Minimum Traded Quantity:
    # - 0.0001 for Kraken/BTC
    min_quantity: float = 0.0001
    # ATR adjustment to support stop loss price
    atr_factor: float = 3.0
