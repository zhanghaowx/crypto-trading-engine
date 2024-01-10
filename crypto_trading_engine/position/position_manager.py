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
        self.positions[symbol] = (
            self.positions[symbol]
            if symbol in self.positions.keys()
            else Position(symbol, 0.0, 0.0)
        )
        self.positions[symbol].volume += quantity
        self.positions[symbol].cash_value += price * quantity

        assert symbol in self.positions.keys()

    def on_sell(self, symbol: str, price: float, quantity: float):
        assert symbol in self.positions.keys()

        self.positions[symbol].volume -= quantity
        self.positions[symbol].cash_value -= price * quantity

        assert self.positions[symbol].volume >= 0
        assert self.positions[symbol].cash_value >= 0
