from dataclasses import dataclass

from jolteon.market_data.core.candlestick import Candlestick


@dataclass
class ShootingStarPattern:
    shooting_star: Candlestick
    body_ratio: float
    upper_shadow_ratio: float
    lower_shadow_ratio: float
