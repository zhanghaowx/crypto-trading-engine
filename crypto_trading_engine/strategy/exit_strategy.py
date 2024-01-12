from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.trade import Trade


class ExitStrategy(Heartbeater):
    """
    ExitStrategy is a type of strategy to help close open positions. It could
    close a position for profit or loss:
        - Profit: When price starts moving in a direction against us
        - Loss: Either the entire account stop loss condition is met,
                or the price is worse than the last support/resist price
    """

    def on_candlestick(self, _: str, candlestick: Candlestick):
        """
        This method checks the current price trend and determines if we
        should wait or close the position.

        Args:
            _:
            candlestick:

        Returns:

        """
        pass

    def on_tob(self):
        """
        This method checks the current position and determines if the
        current cash value is close enough to stop loss.

        Args:
            _:
        Returns:

        """
        pass

    def on_fill(self, _: str, trade: Trade):
        """
        Re-evaluate the current position and check if we should close it.
        Args:
            _:
            trade:

        Returns:

        """
        pass
