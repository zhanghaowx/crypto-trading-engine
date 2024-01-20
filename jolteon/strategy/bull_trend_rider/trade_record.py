from typing import Union

from jolteon.core.side import MarketSide
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.trade import Trade
from jolteon.strategy.bull_trend_rider.trade_opportunity import (
    TradeOpportunity,
)


class TradeRecord:
    """
    Represents a round trip including a buy and a sell order to lock a profit
    by buying low and selling high.
    """

    buy_order: Union[Order, None]
    buy_trades: list[Trade]
    sell_order: Union[Order, None]
    sell_trades: list[Trade]
    opportunity: TradeOpportunity

    def __init__(
        self,
        opportunity: TradeOpportunity,
        buy_order: Order | None = None,
        sell_order: Order | None = None,
    ):
        self.opportunity = opportunity
        self.buy_order = buy_order
        self.buy_trades = []
        self.sell_order = sell_order
        self.sell_trades = []

        assert not self.buy_order or self.buy_order.side == MarketSide.BUY
        assert not self.sell_order or self.sell_order.side == MarketSide.SELL

        assert all(trade.side == MarketSide.BUY for trade in self.buy_trades)
        assert all(trade.side == MarketSide.SELL for trade in self.sell_trades)

    def completed(self) -> bool:
        return (
            self.buy_order is not None
            and self.sell_order is not None
            and len(self.buy_trades) > 0
            and len(self.sell_trades) > 0
            and sum(x.quantity for x in self.buy_trades)
            >= self.buy_order.quantity
            and sum(x.quantity for x in self.sell_trades)
            >= self.sell_order.quantity
        )

    def should_sell_for_loss(self, market_price: float) -> bool:
        """
        Whether a strategy shall try to close the position even taking a loss

        Args:
            market_price: Current market price of the symbol

        Returns:
            True if we should close the position immediately

        """
        assert (
            not self.sell_order
        ), "No need to check after placing a sell order"
        assert self.buy_order and self.buy_order.side == MarketSide.BUY
        if market_price < self.opportunity.stop_loss_price:
            return True
        return False

    def should_sell_for_profit(self, market_price: float) -> bool:
        """
        Whether a strategy shall try to close the position for a profit

        Args:
            market_price: Current market price of the symbol

        Returns:
            True if we should close the position immediately

        """

        assert (
            not self.sell_order
        ), "No need to check after placing a sell order"
        assert self.buy_order and self.buy_order.side == MarketSide.BUY
        if market_price > self.opportunity.profit_price:
            return True
        return False
