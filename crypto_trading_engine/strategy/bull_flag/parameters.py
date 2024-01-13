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
    # A candlestick needs to be smaller than `threshold * body of previous
    # extremely bullish candlestick` in order to be considered as part of
    # the consolidation period.
    consolidation_period_threshold: float = 0.2
