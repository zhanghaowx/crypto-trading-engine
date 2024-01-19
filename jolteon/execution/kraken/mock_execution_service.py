import uuid
from random import randint

import requests
from blinker import signal

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.kraken.historical_feed import HistoricalFeed


class MockExecutionService(Heartbeater):
    def __init__(self):
        """
        Creates a mock execution service to act as the exchange. It will
        respond to requests such as buy and sell, and based on the most
        recent market trade at the exchange, it will generate fake fill
        notices.

        Please be aware that the order book won't change after a trade.
        As a result, you might never able to clear a whole price level
        using market orders. Keep this limitation in mind when
        testing your strategy.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")

    def on_order(self, sender: object, order: Order):
        """
        Place an order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            sender: Name of the sender of the order request
            order: Details about the order including symbol, price and quantity

        Returns:
            None

        """
        # Record every order in history
        self.order_history[order.client_order_id] = order

        # Get a random market trader near the fake time and do a match
        # close to the market in history
        price = self._get_closest_market_trade_price(order.symbol)
        self._generate_order_fill(
            order=order,
            filled_price=price,
        )

    # noinspection PyArgumentList
    @staticmethod
    def _get_closest_market_trade_price(symbol) -> float:
        now = time_manager().now()

        # First search in the cache
        for trades in HistoricalFeed.CACHE.values():
            for trade in trades:
                if abs(trade.transaction_time - now).total_seconds() < 15:
                    return trade.price

        # Second search using Kraken's API
        response = requests.get(
            f"https://api.kraken.com/0/public/Trades?"
            f"pair={symbol}&"
            f"since={int(now.timestamp())}&"
            f"limit=1"
        )
        assert response.status_code == 200, response

        json_resp = response.json()
        assert json_resp["error"] == [], json_resp
        assert json_resp["result"] is not None, json_resp
        return float(json_resp["result"][symbol][0][0])

    def _generate_order_fill(
        self,
        order: Order,
        filled_price: float,
    ):
        trade = Trade(
            trade_id=randint(1, 1000),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=order.side,
            price=filled_price,
            quantity=order.quantity,
            transaction_time=time_manager().now(),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
