from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    """
    What a venue charges to trade, as a fraction of the notional filled.
    The maker rate applies to an order that rested on the book before it
    filled, the taker rate to one that crossed to fill immediately.
    """

    maker_rate: float
    taker_rate: float

    def maker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.maker_rate

    def taker_fee(self, price: float, quantity: float) -> float:
        return price * quantity * self.taker_rate


# Kraken's base tier, per https://www.kraken.com/features/fee-schedule.
# The rates fall with 30 day volume, so an account trading above base
# tier needs its own schedule rather than this one.
KRAKEN = FeeSchedule(maker_rate=0.0025, taker_rate=0.0040)
