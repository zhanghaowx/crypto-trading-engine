import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import pytz
from requests import Response

from jolteon.engine.core.engine_run import ExecutionMode
from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.execution_simulation import (
    ExecutionSimulationSettings,
)
from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.health_monitor.heartbeat import (
    Heartbeater,
)
from jolteon.engine.core.parameter.parameter_service import ParameterValues
from jolteon.engine.core.retry import Retry
from jolteon.engine.core.sentry.reporting import (
    capture_operational_exception,
)
from jolteon.engine.execution.kraken.parameters import (
    KrakenExecutionParameters,
)
from jolteon.engine.execution.kraken.rest_client import KrakenRESTClient
from jolteon.engine.execution.unique_trade_id import unique_trade_id
from jolteon.engine.market_data.core.order import CancelOrder, Order
from jolteon.engine.market_data.core.trade import Trade

_EXCHANGE = "Kraken"

# https://docs.kraken.com/api-reference/trading/add-order
_ADD_ORDER_API = "/0/private/AddOrder"
# https://docs.kraken.com/api-reference/trading/cancel-order
_CANCEL_ORDER_API = "/0/private/CancelOrder"
# https://docs.kraken.com/api-reference/account-data/query-orders-info
_QUERY_ORDERS_API = "/0/private/QueryOrders"
# https://docs.kraken.com/api-reference/account-data/query-trades-info
_QUERY_TRADES_API = "/0/private/QueryTrades"
_QUERY_TRADES_MAX_IDS = 20


class ExecutionService(Heartbeater, SignalSubscriber):
    # This service books orders at Kraken. Simulated execution is a
    # different service selected when the runtime is assembled.
    execution_mode = ExecutionMode.REAL

    @dataclass
    class ErrorCode(StrEnum):
        NOT_CONFIGURED = "NOT_CONFIGURED"
        CREATE_ORDER_FAILURE = "CREATE_ORDER_FAILURE"
        GET_TRADE_FAILURE = "GET_TRADE_FAILURE"
        CANCEL_ORDER_FAILURE = "CANCEL_ORDER_FAILURE"

    def __init__(
        self,
        poll_interval=None,
        max_retries=None,
        health_monitor: HealthMonitor | None = None,
    ):
        """
        Creates an execution service to act as the exchange. It will
        respond to requests such as buy and sell.

        Args:
            poll_interval: Interval in seconds to poll trade information for
                           the just sent orders
            max_retries: Number of attempts to confirm fills

        """
        super().__init__(type(self).__name__, health_monitor=health_monitor)
        self._client = KrakenRESTClient()
        self._poll_interval = poll_interval
        self._fill_retries = max_retries
        self._configured = all(
            value is not None
            for value in (
                self._poll_interval,
                self._fill_retries,
            )
        )

        self.order_history = dict[str, Order]()
        self._reported_fills: dict[str, Decimal] = {}
        self.order_fill_event = signal("order_fill")
        self._health_monitor = health_monitor
        assert os.environ.get("KRAKEN_API_KEY"), (
            "Please set the KRAKEN_API_KEY environment variable"
        )
        assert os.environ.get("KRAKEN_API_SECRET"), (
            "Please set the KRAKEN_API_SECRET environment variable"
        )

    def configure(self, parameters: ParameterValues, symbol: str) -> None:
        """Apply the validated startup revision before accepting orders."""
        configured = parameters.get(KrakenExecutionParameters, symbol)
        if self._poll_interval is None:
            self._poll_interval = configured.poll_interval
        if self._fill_retries is None:
            self._fill_retries = configured.max_retries
        self._configured = True
        self.remove_issue(self.ErrorCode.NOT_CONFIGURED.name)
        self.mark_healthy()

    def describe_simulation(
        self, symbol: str
    ) -> ExecutionSimulationSettings | None:
        """Real orders use venue outcomes rather than a fill simulation."""
        return None

    def _require_configuration(self) -> None:
        if self._configured:
            return
        self.add_issue(
            HealthState.CRITICAL, self.ErrorCode.NOT_CONFIGURED.name
        )
        raise RuntimeError("Execution configuration has not been delivered")

    @subscribe("order")
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
            self._require_configuration()
        except RuntimeError:
            return
        if self._health_monitor and not self._health_monitor.can_trade:
            return
        try:
            response = self.send_order(order)
            transaction_ids = response.get("result", {}).get("txid", [])

            asyncio.create_task(
                self._poll_fills(transaction_ids=transaction_ids, order=order)
            )

        except Exception as e:
            logging.error(f"Fail to send order: {e}", exc_info=True)
            capture_operational_exception(e, operation="submit_order")

            self.add_issue(
                HealthState.CRITICAL, self.ErrorCode.CREATE_ORDER_FAILURE.name
            )
            return

        # Record every order in history
        self.order_history[order.client_order_id] = order

    @subscribe("cancel_order")
    def on_cancel_order(self, sender: object, cancel_order: CancelOrder):
        """
        Cancel a previously placed order.

        Args:
            sender: Name of the sender of the cancel request
            cancel_order: Identifies the order to cancel

        Returns:
            None

        """
        try:
            self.send_cancel_order(cancel_order)
        except Exception as e:
            logging.error(f"Fail to cancel order: {e}", exc_info=True)
            capture_operational_exception(e, operation="cancel_order")

            self.add_issue(
                HealthState.CRITICAL, self.ErrorCode.CANCEL_ORDER_FAILURE.name
            )
            return

    def send_cancel_order(self, cancel_order: CancelOrder):
        """
        Cancel an order at the exchange.

        The `txid` field accepts either the exchange's own order
        identifier or the `userref` the order was placed with; we placed
        every order under `userref` (see `send_order`), so cancelling by
        that same value is what identifies the order here.

        Args:
            cancel_order: Identifies the order to cancel

        Returns:
            None

        """
        self._require_configuration()
        post_data = {"txid": int(cancel_order.client_order_id)}
        response = self._client.send_request(_CANCEL_ORDER_API, post_data)

        if self._handle_possible_error(
            response, self.ErrorCode.CANCEL_ORDER_FAILURE
        ):
            return

        self.remove_issue(self.ErrorCode.CANCEL_ORDER_FAILURE)
        logging.debug(
            f"CancelOrder request received response from exchange: "
            f"{response.json()}"
        )

    def send_order(self, order):
        """
        Send an order to the exchange.

        Args:
            order:

        Returns:

        """

        self._require_configuration()
        post_data = {
            "pair": order.symbol,
            "type": order.side.value.lower(),
            "ordertype": order.order_type.value.lower(),
            "volume": order.quantity,
            "userref": int(order.client_order_id),
        }
        response = self._client.send_request(_ADD_ORDER_API, post_data)

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
        # A refused order has no transaction ID and therefore no fills to
        # retrieve.
        if len(transaction_ids) == 0:
            return

        async with Retry(
            max_retries=self._fill_retries, delay_seconds=self._poll_interval
        ) as retry:
            await retry.execute(
                self._get_fills, transaction_ids=transaction_ids, order=order
            )

    def _get_fills(self, transaction_ids: list[str], order: Order):
        """Publish individual executions once, including open-order partials.

        QueryOrders aggregates executions; QueryTrades supplies the actual
        prices, quantities, fees, timestamps and stable venue trade IDs.
        """
        if not transaction_ids:
            raise ValueError("Fill polling requires exchange order IDs")
        orders = self._query_fills(
            _QUERY_ORDERS_API,
            {
                "txid": ",".join(transaction_ids),
                "userref": order.client_order_id,
                "trades": True,
                "consolidate_taker": False,
            },
        )
        if set(orders) != set(transaction_ids):
            raise RuntimeError(
                "QueryOrders did not return all requested orders"
            )

        execution_orders: dict[str, str] = {}
        for exchange_order_id, details in orders.items():
            if details["descr"]["type"] != order.side.value.lower():
                raise ValueError(
                    "QueryOrders returned an unexpected order side"
                )
            for exchange_execution_id in details.get("trades", []):
                previous = execution_orders.setdefault(
                    exchange_execution_id, exchange_order_id
                )
                if previous != exchange_order_id:
                    raise ValueError(
                        "One execution belongs to multiple orders"
                    )

        unseen = [
            execution_id
            for execution_id, order_id in execution_orders.items()
            if unique_trade_id(_EXCHANGE, order_id, execution_id)
            not in self._reported_fills
        ]
        executions: dict[str, dict] = {}
        for start in range(0, len(unseen), _QUERY_TRADES_MAX_IDS):
            batch = unseen[start : start + _QUERY_TRADES_MAX_IDS]
            details = self._query_fills(
                _QUERY_TRADES_API, {"txid": ",".join(batch)}
            )
            if set(details) != set(batch):
                raise RuntimeError("QueryTrades omitted requested executions")
            executions.update(details)

        fills = []
        for execution_id, details in executions.items():
            order_id = execution_orders[execution_id]
            if details["ordertxid"] != order_id:
                raise ValueError("Execution belongs to an unexpected order")
            if details["type"] != order.side.value.lower():
                raise ValueError("Execution has an unexpected side")
            fills.append(
                Trade(
                    exchange_trade_id=int(details["trade_id"]),
                    unique_trade_id=unique_trade_id(
                        _EXCHANGE, order_id, execution_id
                    ),
                    client_order_id=order.client_order_id,
                    exchange=_EXCHANGE,
                    exchange_order_id=order_id,
                    exchange_execution_id=execution_id,
                    symbol=order.symbol,
                    maker_order_id="",
                    taker_order_id="",
                    side=order.side,
                    price=float(details["price"]),
                    fee=float(details["fee"]),
                    quantity=float(details["vol"]),
                    transaction_time=datetime.fromtimestamp(
                        details["time"], tz=pytz.utc
                    ),
                )
            )

        # Validate the whole response before publishing any part of it.
        quantities = {
            execution_id: self._reported_fills[key]
            for execution_id, order_id in execution_orders.items()
            if (key := unique_trade_id(_EXCHANGE, order_id, execution_id))
            in self._reported_fills
        }
        quantities.update(
            {key: Decimal(value["vol"]) for key, value in executions.items()}
        )
        for order_id, details in orders.items():
            total = sum(
                (quantities[key] for key in details.get("trades", [])),
                Decimal(0),
            )
            if total != Decimal(details["vol_exec"]):
                raise RuntimeError(
                    "Execution quantities do not match the order"
                )

        for trade in sorted(
            fills,
            key=lambda fill: (fill.transaction_time, fill.unique_trade_id),
        ):
            # Mark before dispatch: a receiver failure must not make a later
            # poll account for the same execution twice.
            self._reported_fills[trade.unique_trade_id] = Decimal(
                executions[trade.exchange_execution_id]["vol"]
            )
            self.order_fill_event.send(self.order_fill_event, trade=trade)

        if any(
            details["status"] not in {"closed", "canceled", "expired"}
            for details in orders.values()
        ):
            raise RuntimeError("Order is still open; continue polling fills")

    def _query_fills(self, endpoint: str, payload: dict) -> dict:
        response = self._client.send_request(endpoint, payload)
        if self._handle_possible_error(
            response, self.ErrorCode.GET_TRADE_FAILURE
        ):
            raise RuntimeError("REST API returned an error on fetching trades")
        self.remove_issue(self.ErrorCode.GET_TRADE_FAILURE)
        return response.json()["result"]

    def _handle_possible_error(
        self, response: Response, error_code: ErrorCode
    ):
        if response.status_code != 200:
            logging.error(f"REST API returned error: {response}")
            self.add_issue(HealthState.CRITICAL, error_code.name)
            return True

        possible_error = response.json().get("error")
        if possible_error:
            logging.error(
                f"REST API returned error: {possible_error}, "
                f"full response: {response.json()}"
            )
            self.add_issue(HealthState.CRITICAL, error_code.name)
            return True
        return False
