from dataclasses import dataclass

from jolteon.core.event.signal import subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.side import MarketSide
from jolteon.market_data.core.trade import Trade


@dataclass
class Position:
    symbol: str
    volume: float
    cash_value: float


class PositionManager(SignalSubscriber):
    def __init__(self):
        """
        Manages all bought securities and their positions
        """
        self.positions = dict[str, Position]()
        self.pnl = float(0.0)

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        if trade.side == MarketSide.BUY:
            self._on_buy(trade.symbol, trade.price, trade.fee, trade.quantity)
        elif trade.side == MarketSide.SELL:
            self._on_sell(trade.symbol, trade.price, trade.fee, trade.quantity)
        else:
            assert False, f"Trade has an invalid trade side: {trade}"

    def _on_buy(self, symbol: str, price: float, fee: float, quantity: float):
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
        self.pnl = self.pnl - price * quantity - fee

        assert symbol in self.positions.keys()
        return self.positions[symbol]

    def _on_sell(self, symbol: str, price: float, fee: float, quantity: float):
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
        self.pnl = self.pnl + price * quantity - fee

        assert (
            self.positions[symbol].volume >= -1e-10
        ), f"Unexpected negative volume for {self.positions}"

        return self.positions[symbol]
