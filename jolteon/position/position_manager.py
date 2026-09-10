from dataclasses import dataclass

from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.side import MarketSide
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.trade import Trade


@dataclass
class Position:
    symbol: str
    volume: float
    cash_value: float


@dataclass
class PositionUpdate:
    symbol: str
    volume: float


class PositionManager(SignalSubscriber):
    def __init__(self):
        """
        Manages all bought securities and their positions
        """
        self.positions = dict[str, Position]()
        self.pnl = float(0.0)
        self._mark_prices = dict[str, float]()
        self.position_updated_event = signal("position_updated")

    @property
    def total_pnl(self) -> float:
        """
        Realized PnL plus the mark-to-market value of open positions, using
        the latest mid-price seen for each symbol. Matters for strategies
        that hold inventory (e.g. market making), where realized PnL alone
        hides the risk sitting in open positions.
        """
        mark_to_market = sum(
            position.volume * self._mark_prices.get(symbol, 0.0)
            for symbol, position in self.positions.items()
        )
        return self.pnl + mark_to_market

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self._mark_prices[bbo.symbol] = (bbo.bid_price + bbo.ask_price) / 2

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        if trade.side == MarketSide.BUY:
            self._on_buy(trade.symbol, trade.price, trade.fee, trade.quantity)
        elif trade.side == MarketSide.SELL:
            self._on_sell(trade.symbol, trade.price, trade.fee, trade.quantity)
        else:
            assert False, f"Trade has an invalid trade side: {trade}"

        self.position_updated_event.send(
            self.position_updated_event,
            position_update=PositionUpdate(
                symbol=trade.symbol,
                volume=self._position_for(trade.symbol).volume,
            ),
        )

    def _position_for(self, symbol: str) -> Position:
        """
        The tracked position for `symbol`, opened flat if it is new.
        """
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol, 0.0, 0.0)
        return self.positions[symbol]

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
        position = self._position_for(symbol)
        position.volume += quantity
        position.cash_value += price * quantity
        self.pnl = self.pnl - price * quantity - fee

        return position

    def _on_sell(self, symbol: str, price: float, fee: float, quantity: float):
        """
        Removes the sell trade from tracked positions

        A position may be long or short: selling more than is held leaves
        volume negative, and the cash accounting carries the sign through.

        Args:
            symbol: Symbol of the security/cryptocurrency just traded
            price: Price of the trade
            quantity: Quantity of the trade
        Returns:
            Current position of the traded symbol
        """
        position = self._position_for(symbol)
        position.volume -= quantity
        position.cash_value -= price * quantity
        self.pnl = self.pnl + price * quantity - fee

        return position
