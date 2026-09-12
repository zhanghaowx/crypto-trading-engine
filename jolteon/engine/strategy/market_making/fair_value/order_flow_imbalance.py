from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.market_data.core.book_features import imbalance
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    OrderFlowImbalanceParameters,
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

    Returns 0.0 when no depth is available.
    """

    def __init__(
        self,
        scale: float | None = None,
        depth: int | None = None,
        parameter_service: IParameterService | None = None,
    ):
        assert depth is None or depth > 0, "depth must be positive"
        self._scale = scale
        self._depth = depth
        self._parameter_service = parameter_service or StaticParameterService()

    @property
    def name(self) -> str:
        return "order_flow_imbalance"

    def adjustment(self, context: BookSnapshot) -> float:
        params = self._parameter_service.get(
            OrderFlowImbalanceParameters, context.bbo.symbol
        )
        depth = self._depth if self._depth is not None else params.depth
        scale = self._scale if self._scale is not None else params.scale
        skew = imbalance(context.bids[:depth], context.asks[:depth])
        half_spread = (context.bbo.ask_price - context.bbo.bid_price) / 2
        return scale * skew * half_spread
