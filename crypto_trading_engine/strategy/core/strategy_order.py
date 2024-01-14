from dataclasses import dataclass

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.order import Order
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


@dataclass(frozen=True, order=True)
class StrategyOrder:
    """
    Represents an order from a strategy, whose position is not closed yet.
    It includes details about the order and other data used by the strategy
    for placing the order.
    """

    opportunity: TradeOpportunity
    open_order: Order

    def should_close_for_loss(self, market_price: float) -> bool:
        assert self.open_order.side == MarketSide.BUY
        if market_price < self.opportunity.stop_loss_price:
            return True
        return False

    def should_close_for_profit(self, market_price: float) -> bool:
        assert self.open_order.side == MarketSide.BUY
        if market_price > self.opportunity.profit_price:
            return True
        return False
