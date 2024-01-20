import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import pytz
from blinker import signal
from kraken import spot

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.trade import Trade


class ExecutionService(Heartbeater):
    @dataclass
    class ErrorCode(StrEnum):
        CREATE_ORDER_FAILURE = "CREATE_ORDER_FAILURE"
        GET_TRADE_FAILURE = "GET_TRADE_FAILURE"

    def __init__(self, dry_run=True):
        """
        Creates an execution service to act as the exchange. It will
        respond to requests such as buy and sell.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")
        self._dry_run = dry_run
        self._order_client = spot.trade.Trade(
            key=os.environ.get("KRAKEN_API_KEY"),
            secret=os.environ.get("KRAKEN_API_SECRET"),
        )
        self._user_client = spot.user.User(
            key=os.environ.get("KRAKEN_API_KEY"),
            secret=os.environ.get("KRAKEN_API_SECRET"),
        )

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

        # Calling AddOrder/addOrder with the validate parameter set to true
        # (validate=1, validate=true, validate=anything, etc.) will cause the
        # order details to be checked for errors, but the API response will
        # never include an order ID (which would always be returned for a
        # successful order without the validate parameter).
        response = self._order_client.create_order(
            ordertype=order.order_type.value.lower(),
            side=order.side.value.lower(),
            volume=order.quantity,
            pair=order.symbol,
            price=order.price,
            userref=int(order.client_order_id),
            validate=self._dry_run,
        )
        logging.info(f"Create order: {response}")

        if not self.__handle_possible_error(
            response, self.ErrorCode.CREATE_ORDER_FAILURE
        ):
            self.remove_issue(self.ErrorCode.CREATE_ORDER_FAILURE)

        # Record every order in history
        self.order_history[order.client_order_id] = order

        if not self._dry_run:
            asyncio.create_task(self._poll_fills(order))

    # Poll for trade confirmations
    async def _poll_fills(self, order: Order):
        while not self._get_fills(order):
            await asyncio.sleep(1)

    def _get_fills(self, order: Order):
        response = self._user_client.get_closed_orders(
            userref=int(order.client_order_id), trades=True
        )

        if self.__handle_possible_error(
            response, self.ErrorCode.GET_TRADE_FAILURE
        ):
            return False

        self.remove_issue(self.ErrorCode.GET_TRADE_FAILURE)

        trades = list[Trade]()
        for json_trade in response["result"]["closed"].values():
            if json_trade["userref"] != int(order.client_order_id):
                continue

            assert json_trade["userref"] == int(order.client_order_id)
            logging.info(f"Found trade {json_trade}")
            trades.append(
                Trade(
                    trade_id=0,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    maker_order_id="",
                    taker_order_id="",
                    side=order.side,
                    price=float(json_trade["price"]),
                    quantity=float(json_trade["vol_exec"]),
                    transaction_time=datetime.fromtimestamp(
                        int(json_trade["closetm"]), tz=pytz.utc
                    ),
                )
            )

        if sum([trade.quantity for trade in trades]) >= order.quantity:
            for trade in trades:
                self.order_fill_event.send(
                    self.order_fill_event,
                    trade=trade,
                )
            return True

        return False

    def __handle_possible_error(self, response: dict, error_code: ErrorCode):
        possible_error = response.get("error")
        if possible_error:
            logging.error(f"REST API returned error: {response}")
            self.add_issue(HeartbeatLevel.ERROR, error_code.name)
            return True
        return False
