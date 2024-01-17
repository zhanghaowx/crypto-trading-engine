from dataclasses import dataclass


@dataclass
class TradeOpportunity:
    # Score of this opportunity
    score: float = 0.0

    # When crossed, strategy shall sell for a loss to limit damages
    stop_loss_price: float = 0.0

    # When crossed, strategy shall sell some or all positions for a profit
    profit_price: float = 0.0

    def good(self, min_score: float) -> bool:
        return self.score > min_score
