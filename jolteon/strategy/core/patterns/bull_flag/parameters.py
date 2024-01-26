from dataclasses import dataclass


@dataclass(frozen=True)
class BullFlagParameters:
    """
    Parameters for recognizing a bull flag.
    """

    # Whether only publish bull flag opportunities or publish every evaluated
    # opportunities
    verbose: bool = False
    # Maximum number of candlesticks to keep in the pattern recognizer
    max_number_of_recent_candlesticks: int = 15
    # Maximum number of candlesticks to check before the bull flag candlestick
    max_number_of_pre_bull_flag_candlesticks: int = 2
    max_number_of_consolidation_candlesticks: int = 5
    # A candlestick's body needs to be larger than `threshold * body of its
    # previous candlestick` in order to be considered as an extremely
    # bullish candlestick and potentially marked as the starting of a
    # bull flag.
    #
    # Recommendation:
    # Set at least 2.0
    extreme_bullish_threshold: float = 3.0
    # A candlestick's return percentage needs to be larger than X in
    # order to be considered as an extremely bullish candlestick and
    # potentially marked as the starting of a bull flag
    #
    # Recommendation:
    # Pick the 75th/90th percentile return percentage from all candlesticks of
    # the previous day
    extreme_bullish_return_pct: float = 0.00075
    # A candlestick needs to be smaller than `threshold * body of previous
    # extremely bullish candlestick` in order to be considered as part of
    # the consolidation period.
    #
    # Recommendation:
    # Better to keep below 1.0 / extreme_bullish_threshold
    consolidation_period_threshold_cutoff: float = 0.3
