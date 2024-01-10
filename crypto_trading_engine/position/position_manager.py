from dataclasses import dataclass


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
        self.positions: dict[str, Position] = {}

    def on_buy(self, symbol: str, price: float, quantity: float):
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

        assert symbol in self.positions.keys()
        return self.positions[symbol]

    def on_sell(self, symbol: str, price: float, quantity: float):
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

        assert self.positions[symbol].volume >= 0
        assert self.positions[symbol].cash_value >= 0
        return self.positions[symbol]
