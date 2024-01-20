from dataclasses import dataclass


@dataclass(frozen=True)
class BullFlagParameters:
    """
    Parameters for recognizing a bull flag.
    """

    verbose: bool = True
    # Maximum number of candlesticks to keep in the pattern recognizer
    max_number_of_recent_candlesticks: int = 15
    # A candlestick's body needs to be larger than `threshold * body of its
    # previous candlestick` in order to be considered as an extremely
    # bullish candlestick and potentially marked as the starting of a
    # bull flag.
    extreme_bullish_threshold: float = 2.0
    # A candlestick's return percentage needs to be larger than X in
    # order to be considered as an extremely bullish candlestick and
    # potentially marked as the starting of a bull flag
    extreme_bullish_return_pct: float = 0.001
    # A candlestick needs to be smaller than `threshold * body of previous
    # extremely bullish candlestick` in order to be considered as part of
    # the consolidation period.
    consolidation_period_threshold_cutoff: float = 0.2
