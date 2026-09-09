from jolteon.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
    IFairPriceModel,
)


class MidPriceFairPriceModel(IFairPriceModel):
    """
    Simplest possible fair price model: the mid-point between the best bid
    and the best ask. Intended as a starting point that can be replaced by
    a more sophisticated model (e.g. one that also accounts for inventory
    or volatility) without changing anything else in the strategy.
    """

    def calculate(self, context: FairPriceContext) -> float:
        return (context.bbo.bid_price + context.bbo.ask_price) / 2
