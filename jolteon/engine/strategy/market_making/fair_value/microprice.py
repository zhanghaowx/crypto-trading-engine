from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    MicropriceParameters,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class MicropriceAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price toward the side of the book with less resting size -
    a size-weighted view of order flow imbalance computable from the BBO
    alone, so it subscribes to nothing and still works on a feed that
    carries no depth.
    """

    def __init__(
        self,
        scale: float | None = None,
        parameter_service: IParameterService | None = None,
    ):
        self._scale = scale
        self._parameter_service = parameter_service or StaticParameterService()

    @property
    def name(self) -> str:
        return "microprice"

    def adjustment(self, context: BookSnapshot) -> float:
        bbo = context.bbo
        total_quantity = bbo.bid_quantity + bbo.ask_quantity
        if total_quantity <= 0:
            return 0.0

        microprice = (
            bbo.bid_quantity * bbo.ask_price + bbo.ask_quantity * bbo.bid_price
        ) / total_quantity
        mid = (bbo.bid_price + bbo.ask_price) / 2
        scale = self._scale
        if scale is None:
            scale = self._parameter_service.get(
                MicropriceParameters, bbo.symbol
            ).scale
        return scale * (microprice - mid)
