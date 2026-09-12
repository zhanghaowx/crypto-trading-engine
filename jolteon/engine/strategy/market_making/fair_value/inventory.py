from jolteon.engine.core.event.signal import subscribe
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.position.position_manager import PositionUpdate
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    InventoryAdjustmentParameters,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)


class InventoryAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price against the current position: long inventory quotes
    a lower fair price (less eager to buy more, more eager to sell) and
    short quotes a higher one, working the position back toward flat.
    Softens the approach to a hard inventory cap; it does not replace it.
    Sources its own view from position_updated rather than market data,
    proving an adjustment can draw on engine state as readily as a signal
    or the BBO.

    The skew is stated as how far the fair price moves at a full
    position, and divided by the cap each time rather than once, so
    changing the cap moves both together instead of leaving the skew
    calibrated to a cap that no longer applies.
    """

    def __init__(
        self,
        scale: float | None = None,
        parameter_service: IParameterService | None = None,
    ):
        self._scale = scale
        self._parameter_service = parameter_service or StaticParameterService()
        self._volume: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "inventory"

    def adjustment(self, context: BookSnapshot) -> float:
        symbol = context.bbo.symbol
        volume = self._volume.get(symbol, 0.0)
        return -self._scale_for(symbol) * volume

    def _scale_for(self, symbol: str) -> float:
        if self._scale is not None:
            return self._scale
        # One read for both groups: taken separately they could fall
        # either side of a retune and pair a new skew with an old cap.
        values = self._parameter_service.values()
        skew = values.get(
            InventoryAdjustmentParameters, symbol
        ).skew_at_max_inventory
        cap = values.get(MarketMakingParameters, symbol).max_inventory
        return skew / cap

    @subscribe("position_updated")
    def on_position_updated(self, _: str, position_update: PositionUpdate):
        self._volume[position_update.symbol] = position_update.volume
