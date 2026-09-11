from jolteon.engine.core.event.signal import subscribe
from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.trade import Trade
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
        self, scale: float = 1.0, decay: float = 0.9, min_trades: int = 5
    ):
        self._scale = scale
        self._decay = decay
        self._min_trades = min_trades
        self._flow = 0.0
        self._trades_seen = 0

    @property
    def name(self) -> str:
        return "momentum"

    def adjustment(self, context: BookSnapshot) -> float:
        if self._trades_seen < self._min_trades:
            return 0.0
        return self._scale * self._flow

    @subscribe("market_trade_feed")
    def on_trade(self, _: str, market_trade: Trade):
        signed_quantity = (
            market_trade.quantity
            if market_trade.side == MarketSide.BUY
            else -market_trade.quantity
        )
        self._flow = (
            self._decay * self._flow + (1 - self._decay) * signed_quantity
        )
        self._trades_seen += 1
