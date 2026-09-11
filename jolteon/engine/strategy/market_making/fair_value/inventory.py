from jolteon.engine.core.event.signal import subscribe
from jolteon.engine.position.position_manager import PositionUpdate
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class InventoryAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price against the current position: long inventory quotes
    a lower fair price (less eager to buy more, more eager to sell) and
    short quotes a higher one, working the position back toward flat.
    Softens the approach to InventoryLimit's hard cap
    (MarketMakingStrategy); it does not replace it. Sources its own view
    from position_updated rather than market data, proving an adjustment
    can draw on engine state as readily as a signal or the BBO.
    """

    def __init__(self, scale: float = 1.0):
        self._scale = scale
        self._volume: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "inventory"

    def adjustment(self, context: FairPriceContext) -> float:
        volume = self._volume.get(context.bbo.symbol, 0.0)
        return -self._scale * volume

    @subscribe("position_updated")
    def on_position_updated(self, _: str, position_update: PositionUpdate):
        self._volume[position_update.symbol] = position_update.volume
