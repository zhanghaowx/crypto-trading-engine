from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class MicropriceAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price toward the side of the book with less resting size -
    a size-weighted view of order flow imbalance computable from the BBO
    alone, so it subscribes to nothing. A poor cousin of true order-flow
    imbalance (STRATEGY.md Part 3), until an L2 feed exists.
    """

    def __init__(self, scale: float = 1.0):
        self._scale = scale

    @property
    def name(self) -> str:
        return "microprice"

    def adjustment(self, context: FairPriceContext) -> float:
        bbo = context.bbo
        total_quantity = bbo.bid_quantity + bbo.ask_quantity
        if total_quantity <= 0:
            return 0.0

        microprice = (
            bbo.bid_quantity * bbo.ask_price + bbo.ask_quantity * bbo.bid_price
        ) / total_quantity
        mid = (bbo.bid_price + bbo.ask_price) / 2
        return self._scale * (microprice - mid)
