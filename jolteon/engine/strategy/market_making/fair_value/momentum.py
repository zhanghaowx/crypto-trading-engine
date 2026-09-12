from jolteon.engine.core.event.signal import subscribe
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    MomentumParameters,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


class MomentumAdjustment(IFairPriceAdjustment):
    """
    Shifts fair price in the direction of recent signed trade flow, an
    EWMA over market_trade_feed prints - a run of buys nudges fair up, a
    run of sells nudges it down. Returns 0.0 until min_trades prints have
    been seen, so a cold start does not move the quote.
    """

    def __init__(
        self,
        scale: float | None = None,
        decay: float | None = None,
        min_trades: int | None = None,
        parameter_service: IParameterService | None = None,
    ):
        self._scale = scale
        self._decay = decay
        self._min_trades = min_trades
        self._parameter_service = parameter_service or StaticParameterService()
        self._flow = 0.0
        self._trades_seen = 0

    def _parameters(self) -> MomentumParameters:
        return self._parameter_service.get(MomentumParameters)

    @property
    def name(self) -> str:
        return "momentum"

    def adjustment(self, context: BookSnapshot) -> float:
        params = self._parameters()
        min_trades = (
            self._min_trades
            if self._min_trades is not None
            else params.min_trades
        )
        if self._trades_seen < min_trades:
            return 0.0
        scale = self._scale if self._scale is not None else params.scale
        return scale * self._flow

    @subscribe("market_trade_feed")
    def on_trade(self, _: str, market_trade: Trade):
        signed_quantity = (
            market_trade.quantity
            if market_trade.side == MarketSide.BUY
            else -market_trade.quantity
        )
        decay = (
            self._decay
            if self._decay is not None
            else self._parameters().decay
        )
        self._flow = decay * self._flow + (1 - decay) * signed_quantity
        self._trades_seen += 1
