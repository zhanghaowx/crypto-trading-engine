from jolteon.engine.market_data.core.book_features import imbalance
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class OrderFlowImbalanceAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price toward the side of the book holding less resting
    size, measured across the levels behind the touch rather than the two
    quantities at it. The shift is a fraction of the spread, so it stays
    proportionate to how wide the market is, and `scale` caps it: a
    completely one-sided book moves fair price by `scale` half-spreads.

    Returns 0.0 on a feed that publishes no depth, and during replay.
    """

    def __init__(self, scale: float = 1.0, depth: int = 10):
        assert depth > 0, "depth must be positive"
        self._scale = scale
        self._depth = depth

    @property
    def name(self) -> str:
        return "order_flow_imbalance"

    def adjustment(self, context: FairPriceContext) -> float:
        order_book = context.order_book
        if not order_book:
            return 0.0

        skew = imbalance(
            order_book.bids(self._depth), order_book.asks(self._depth)
        )
        half_spread = (context.bbo.ask_price - context.bbo.bid_price) / 2
        return self._scale * skew * half_spread
