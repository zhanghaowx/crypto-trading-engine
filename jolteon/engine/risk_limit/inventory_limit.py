from jolteon.engine.core.parameter.parameter_service import (
    ALL_SYMBOLS,
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)


class InventoryLimit:
    """
    A hard cap on inventory: once the tracked position on a side reaches
    the configured maximum, quoting on that side is blocked until fills
    bring the position back within bounds.

    The cap is read whenever it is needed rather than copied once, so
    raising or lowering it takes effect on the next quote. A caller that
    passes an explicit maximum gets that one and nothing else.

    This intentionally does not implement IRiskLimit. That interface's
    side-agnostic can_send()/do_send() doesn't fit a limit whose answer
    depends on which side of the market is being quoted.
    """

    def __init__(
        self,
        max_inventory: float | None = None,
        parameter_service: IParameterService | None = None,
        symbol: str = ALL_SYMBOLS,
    ):
        assert max_inventory is None or max_inventory > 0, (
            "max_inventory must be positive"
        )
        self._fixed_max_inventory = max_inventory
        self._parameter_service = parameter_service or StaticParameterService()
        self._symbol = symbol
        self._position = 0.0

    @property
    def position(self) -> float:
        return self._position

    @property
    def max_inventory(self) -> float:
        if self._fixed_max_inventory is not None:
            return self._fixed_max_inventory
        return self._parameter_service.get(
            MarketMakingParameters, self._symbol
        ).max_inventory

    def record_fill(self, trade: Trade) -> None:
        if trade.side == MarketSide.BUY:
            self._position += trade.quantity
        elif trade.side == MarketSide.SELL:
            self._position -= trade.quantity

    def can_quote(self, side: MarketSide) -> bool:
        maximum = self.max_inventory
        if side == MarketSide.BUY:
            return self._position < maximum
        elif side == MarketSide.SELL:
            return self._position > -maximum
        return False
