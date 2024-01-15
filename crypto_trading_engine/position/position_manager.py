from dataclasses import dataclass

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.trade import Trade


@dataclass
class Position:
    symbol: str
    volume: float
    cash_value: float


class PositionManager:
    def __init__(self):
        """
        Manages all bought securities and their positions
        """
        self.positions = dict[str, Position]()
        self.pnl = float(0.0)

    def on_fill(self, _: str, trade: Trade):
        if trade.side == MarketSide.BUY:
            self._on_buy(trade.symbol, trade.price, trade.quantity)
        elif trade.side == MarketSide.SELL:
            self._on_sell(trade.symbol, trade.price, trade.quantity)
        else:
            assert False, f"Trade has an invalid trade side: {trade}"

    def _on_buy(self, symbol: str, price: float, quantity: float):
        """
        Adds the buy trade to tracked positions

        Args:
            symbol: Symbol of the security/cryptocurrency just traded
            price: Price of the trade
            quantity: Quantity of the trade
        Returns:
            Current position of the traded symbol
        """
        self.positions[symbol] = (
            self.positions[symbol]
            if symbol in self.positions.keys()
            else Position(symbol, 0.0, 0.0)
        )
        self.positions[symbol].volume += quantity
        self.positions[symbol].cash_value += price * quantity
        self.pnl -= price * quantity

        assert symbol in self.positions.keys()
        return self.positions[symbol]

    def _on_sell(self, symbol: str, price: float, quantity: float):
        """
        Removes the sell trade from tracked positions

        Args:
            symbol: Symbol of the security/cryptocurrency just traded
            price: Price of the trade
            quantity: Quantity of the trade
        Returns:
            Current position of the traded symbol
        """
        assert symbol in self.positions.keys()

        self.positions[symbol].volume -= quantity
        self.positions[symbol].cash_value -= price * quantity
        self.pnl += price * quantity

        assert (
            self.positions[symbol].volume >= 0
        ), f"Unexpected negative volume for {self.positions}"

        return self.positions[symbol]
