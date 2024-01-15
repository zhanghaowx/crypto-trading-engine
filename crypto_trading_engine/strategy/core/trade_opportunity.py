from dataclasses import dataclass
from typing import ClassVar


@dataclass
class TradeOpportunity:
    # Minimal score for an opportunity to be considered worth trading
    MIN_SCORE: ClassVar[float] = 0.0

    # Score of this opportunity
    score: float = MIN_SCORE

    # When crossed, strategy shall sell for a loss to limit damages
    stop_loss_price: float = 0.0

    # When crossed, strategy shall sell some or all positions for a profit
    profit_price: float = 0.0

    def good(self) -> bool:
        return self.score > self.MIN_SCORE
