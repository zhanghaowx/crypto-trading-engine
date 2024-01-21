from dataclasses import dataclass


@dataclass
class ShootingStarParameters:
    # The body of the candlestick is smaller than body_ratio * (high - low)
    max_body_ratio: float = 0.2
    # Upper shadow of the candlestick is larger than
    # upper_shadow_ratio * abs(open - close)
    min_upper_shadow_ratio: float = 2
    # Lower shadow of the candlestick is smaller than
    # lower_shadow_ratio * (high - low)
    max_lower_shadow_ratio: float = 0.2
