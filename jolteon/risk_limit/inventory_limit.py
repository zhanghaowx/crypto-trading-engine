from jolteon.core.side import MarketSide
from jolteon.market_data.core.trade import Trade


class InventoryLimit:
    """
    A hard cap on inventory: once the tracked position on a side reaches
    the configured maximum, quoting on that side is blocked until fills
    bring the position back within bounds.

    This intentionally does not implement IRiskLimit. That interface's
    side-agnostic can_send()/do_send() doesn't fit a limit whose answer
    depends on which side of the market is being quoted.
    """

    def __init__(self, max_inventory: float):
        assert max_inventory > 0, "max_inventory must be positive"
        self._max_inventory = max_inventory
        self._position = 0.0

    @property
    def position(self) -> float:
        return self._position

    def record_fill(self, trade: Trade) -> None:
        if trade.side == MarketSide.BUY:
            self._position += trade.quantity
        elif trade.side == MarketSide.SELL:
            self._position -= trade.quantity

    def can_quote(self, side: MarketSide) -> bool:
        if side == MarketSide.BUY:
            return self._position < self._max_inventory
        elif side == MarketSide.SELL:
            return self._position > -self._max_inventory
        return False
