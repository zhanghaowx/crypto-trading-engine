from blinker import signal

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.trade import Trade


class BootstrapStrategy(Heartbeater):
    """
    Bootstrap Strategy is a template for future strategies. Simply copy and
    rename this template and the corresponding unit test template files.

    Enjoy coding and testing!
    """

    def __init__(self):
        super().__init__(type(self).__name__, interval_in_seconds=10)
        # Sends order event to execution service.
        self.order_event = signal("order")

    ##########################################################################
    # The following are a few events the strategy might be interested in.
    # - You will need to connect the signal sender for each of them in order
    #   to receive messages.
    # - Remove any event handling method if not related.
    ##########################################################################

    def on_candlestick(self, _: str, candlestick: Candlestick):
        """
        This method checks the candlestick pattern currently in the market
        and make a buy or sell decision.

        Args:
            _: Unique identifier for the sender
            candlestick: Most recent candlestick for the market

        Returns:

        """
        pass

    def on_fill(self, _: str, trade: Trade):
        """
        Notification received when orders are traded. Beware that multiple
        trades may be received for the same order, especially for a large
        quantity.
        Args:
            _: Unique identifier for the sender
            trade: The trade for recently submitted orders

        Returns:
            None
        """
        pass
