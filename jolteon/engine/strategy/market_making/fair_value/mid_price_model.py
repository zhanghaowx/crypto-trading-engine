from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    IFairPriceModel,
)


class MidPriceFairPriceModel(IFairPriceModel):
    """
    Simplest possible fair price model: the mid-point between the best bid
    and the best ask, on both sides. Intended as a starting point that can
    be replaced by a more sophisticated model (e.g. one that skews bid and
    ask apart based on inventory or volatility) without changing anything
    else in the strategy.
    """

    def _calculate(self, context: BookSnapshot) -> FairPrice:
        mid = (context.bbo.bid_price + context.bbo.ask_price) / 2
        return FairPrice(bid=mid, ask=mid)
