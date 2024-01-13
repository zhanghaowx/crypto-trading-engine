from dataclasses import dataclass


@dataclass
class BullFlagOpportunity:
    stop_loss_price: float = 0.0
    score: float = 0.0
