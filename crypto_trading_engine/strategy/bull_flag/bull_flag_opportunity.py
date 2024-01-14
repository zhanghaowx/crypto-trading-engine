from dataclasses import dataclass
from typing import ClassVar


@dataclass
class BullFlagOpportunity:
    MIN_SCORE: ClassVar[float] = 0.0

    stop_loss_price: float = 0.0
    score: float = MIN_SCORE

    def is_worth_buying(self) -> bool:
        return self.score > self.MIN_SCORE
