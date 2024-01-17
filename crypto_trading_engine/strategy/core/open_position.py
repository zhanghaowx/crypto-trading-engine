from dataclasses import dataclass

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.order import Order
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


@dataclass(frozen=True, order=True)
class OpenPosition:
    """
    Represents an order from a strategy, whose position is not closed yet.
    It includes details about the order and other data used by the strategy
    for placing the order.
    """

    opportunity: TradeOpportunity
    order: Order

    def should_close_for_loss(self, market_price: float) -> bool:
        """
        Whether a strategy shall try to close the position even taking a loss

        Args:
            market_price: Current market price of the symbol

        Returns:
            True if we should close the position immediately

        """
        assert self.order.side == MarketSide.BUY
        if market_price < self.opportunity.stop_loss_price:
            return True
        return False

    def should_close_for_profit(self, market_price: float) -> bool:
        """
        Whether a strategy shall try to close the position for a profit

        Args:
            market_price: Current market price of the symbol

        Returns:
            True if we should close the position immediately

        """

        assert self.order.side == MarketSide.BUY
        if market_price > self.opportunity.profit_price:
            return True
        return False
