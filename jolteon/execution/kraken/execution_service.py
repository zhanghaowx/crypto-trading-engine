import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import pytz
from blinker import signal
from requests import Response

from jolteon.core.health_monitor.heartbeat import Heartbeater, HeartbeatLevel
from jolteon.execution.kraken.rest_client import KrakenRESTClient
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.trade import Trade


class ExecutionService(Heartbeater):
    @dataclass
    class ErrorCode(StrEnum):
        CREATE_ORDER_FAILURE = "CREATE_ORDER_FAILURE"
        GET_TRADE_FAILURE = "GET_TRADE_FAILURE"

    def __init__(self, dry_run=False):
        """
        Creates an execution service to act as the exchange. It will
        respond to requests such as buy and sell.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")
        self._dry_run = dry_run
        self._client = KrakenRESTClient()
        assert os.environ.get(
            "KRAKEN_API_KEY"
        ), "Please set the KRAKEN_API_KEY environment variable"
        assert os.environ.get(
            "KRAKEN_API_SECRET"
        ), "Please set the KRAKEN_API_SECRET environment variable"

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
        try:
            response = self.send_order(order)
            transaction_ids = response.get("result", {}).get("txid", [])

            if not self._dry_run:
                asyncio.create_task(
                    self._poll_fills(
                        transaction_ids=transaction_ids, order=order
                    )
                )

        except Exception as e:
            logging.error(f"Fail to send order: {e}", exc_info=True)

            self.add_issue(
                HeartbeatLevel.ERROR, self.ErrorCode.CREATE_ORDER_FAILURE.name
            )
            return

        # Record every order in history
        self.order_history[order.client_order_id] = order

    def send_order(self, order):
        """
        Using the following API to send an order to the exchange.
        https://docs.kraken.com/rest/#tag/Trading/operation/addOrder

        Args:
            order:

        Returns:

        """

        # Calling AddOrder/addOrder with the validate parameter set to true
        # (validate=1, validate=true, validate=anything, etc.) will cause the
        # order details to be checked for errors, but the API response will
        # never include an order ID (which would always be returned for a
        # successful order without the validate parameter).
        post_data = {
            "pair": order.symbol,
            "type": order.side.value.lower(),
            "ordertype": order.order_type.value.lower(),
            "volume": order.quantity,
            "userref": int(order.client_order_id),
            "validate": self._dry_run,
        }
        response = self._client.send_request("/0/private/AddOrder", post_data)

        if self._handle_possible_error(
            response, self.ErrorCode.CREATE_ORDER_FAILURE
        ):
            return

        self.remove_issue(self.ErrorCode.CREATE_ORDER_FAILURE)
        logging.debug(
            f"AddOrder request received response from exchange: "
            f"{response.json()}"
        )
        return response.json()

    # Poll for trade confirmations
    async def _poll_fills(self, transaction_ids: list[str], order: Order):
        # In case of dry run or order sent failure, no transaction ID will be
        # returned, and we don't need to retrieve fill notice.
        if len(transaction_ids) == 0:
            return

        while not self._get_fills(transaction_ids, order):
            await asyncio.sleep(1)

    def _get_fills(self, transaction_ids: list[str], order: Order):
        """
        Use the following API to get fill notice.
        https://docs.kraken.com/rest/#tag/Account-Data/operation/getTradesInfo

        Args:
            transaction_ids: A list of transaction IDs returned from the
                             exchange when market order is sent.
            order: The original market order sent to the exchange
        Returns:
            None
        """

        assert len(transaction_ids) > 0
        response = self._client.send_request(
            "/0/private/QueryTrades",
            {"txid": ",".join(transaction_ids), "trades": True},
        )

        if self._handle_possible_error(
            response, self.ErrorCode.GET_TRADE_FAILURE
        ):
            return False

        self.remove_issue(self.ErrorCode.GET_TRADE_FAILURE)
        logging.debug(
            f"QueryTrades received response from exchange " f"{response}"
        )

        trades = list[Trade]()
        for json_trade in response.json()["result"].values():
            logging.info(f"Found trade {json_trade}")

            # Symbol and pair may not 100% match. For example: BTC/USD vs.
            # XBTUSD
            # assert order.symbol == json_trade["pair"]
            assert order.side.value.lower() == json_trade["type"]
            assert order.order_type.value.lower() == json_trade["ordertype"]
            trades.append(
                Trade(
                    trade_id=0,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    maker_order_id="",
                    taker_order_id="",
                    side=order.side,
                    price=float(json_trade["price"]),
                    quantity=float(json_trade["vol"]),
                    transaction_time=datetime.fromtimestamp(
                        json_trade["time"], tz=pytz.utc
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

    def _handle_possible_error(
        self, response: Response, error_code: ErrorCode
    ):
        if response.status_code != 200:
            logging.error(
                f"REST API returned error: {response}", exc_info=True
            )
            self.add_issue(HeartbeatLevel.ERROR, error_code.name)

        possible_error = response.json().get("error")
        if possible_error:
            logging.error(
                f"REST API returned error: {possible_error}, "
                f"full response: {response.json()}",
                exc_info=True,
            )
            self.add_issue(HeartbeatLevel.ERROR, error_code.name)
            return True
        return False
