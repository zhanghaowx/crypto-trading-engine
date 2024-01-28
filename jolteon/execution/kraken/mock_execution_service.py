import logging
import uuid
from datetime import datetime

import pytz
import requests
from blinker import signal

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.id_generator import id_generator
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.data_source import IDataSource


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
        price = self._get_closest_market_trade_price(order)
        self._generate_order_fill(
            order=order,
            filled_price=price,
        )

    # noinspection PyArgumentList
    @staticmethod
    def _get_closest_market_trade_price(order: Order) -> float:
        cached_trades = IDataSource.TRADE_CACHE.values()

        # First search in the cache
        for trades in cached_trades:
            for trade in trades:
                time_difference = (
                    trade.transaction_time - order.creation_time
                ).total_seconds()
                if 0 < time_difference < 60:
                    return trade.price

        logging.warning(
            f"Fail to generate a trade from "
            f"{sum([len(trade_list) for trade_list in cached_trades])} "
            f"cached trades"
        )

        # Second search using Kraken's API
        response = requests.get(
            f"https://api.kraken.com/0/public/Trades?"
            f"pair={order.symbol}&"
            f"since={int(order.creation_time.timestamp())}&"
            f"limit=10"
        )
        assert response.status_code == 200, response

        json_resp = response.json()
        assert json_resp["error"] == [], json_resp
        assert json_resp["result"] is not None, json_resp

        json_trades = json_resp["result"][order.symbol]
        for json_trade in json_trades:
            transaction_time = datetime.fromtimestamp(
                json_trade[2], tz=pytz.utc
            )
            if transaction_time >= order.creation_time:
                return float(json_trade[0])

        return 0.0

    def _generate_order_fill(
        self,
        order: Order,
        filled_price: float,
    ):
        trade = Trade(
            trade_id=id_generator().next(),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=order.side,
            price=filled_price,
            # Based on https://www.kraken.com/features/fee-schedule
            fee=filled_price * order.quantity * 0.0026,
            quantity=order.quantity,
            transaction_time=time_manager().now(),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
