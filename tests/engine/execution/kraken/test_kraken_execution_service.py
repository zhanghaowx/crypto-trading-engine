import asyncio
import os
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

import pytz

from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.unique_trade_id import unique_trade_id
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.trade import Trade


class TestExecutionService(IsolatedAsyncioTestCase):
    # KRAKEN_API_SECRET comes from Kraken's API documentation. It is not a real
    # one.
    KRAKEN_API_TEST_SECRET = (
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18"
        "fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    )

    @patch.dict(os.environ, {"KRAKEN_API_KEY": "api_key"})
    @patch.dict(
        os.environ,
        {"KRAKEN_API_SECRET": KRAKEN_API_TEST_SECRET},
    )
    async def asyncSetUp(self):
        from jolteon.engine.execution.kraken.execution_service import (
            ExecutionService,
        )

        self.health_monitor = HealthMonitor()
        self.execution_service = ExecutionService(
            dry_run=False,
            poll_interval=0.1,
            health_monitor=self.health_monitor,
        )
        self.execution_service.mark_healthy()
        self.mock_order = Order(
            client_order_id="123",
            order_type=OrderType.MARKET_ORDER,
            symbol="BTC-USD",
            side=MarketSide.BUY,
            price=100,
            quantity=1,
            creation_time=datetime(2024, 1, 1, 0, 0, 0),
        )
        self.create_order_response = {
            "error": [],
            "result": {
                "descr": {"order": "buy 1.25000000 XBTUSD @ limit 27500.0"},
                "txid": ["THVRQM-33VKH-UCI7BS", "TTEUX3-HDAAA-RC2RUO"],
            },
        }
        self.closed_orders_response = {
            "error": [],
            "result": {
                "THVRQM-33VKH-UCI7BS": {
                    "refid": "None",
                    "userref": 0,
                    "status": "closed",
                    "reason": "",
                    "opentm": 1688665496.7808,
                    "closetm": 1688667796.8802,
                    "starttm": 0,
                    "expiretm": 0,
                    "descr": {
                        "pair": "XBTUSD",
                        "type": "buy",
                        "ordertype": "market",
                        "price": "27500.0",
                        "price2": "0",
                        "leverage": "none",
                        "order": "buy 1.25000000 XBTUSD @ limit 27500.0",
                        "close": "",
                    },
                    "vol": "0.02000000",
                    "vol_exec": "0.02000000",
                    "cost": "27526.2",
                    "fee": "26.2",
                    "price": "30010.0",
                    "stopprice": "0.00000",
                    "limitprice": "0.00000",
                    "misc": "",
                    "oflags": "fciq",
                    "trigger": "index",
                    "trades": ["TZX2WP-XSEOP-FP7WYR"],
                },
                "TTEUX3-HDAAA-RC2RUO": {
                    "refid": "None",
                    "userref": 0,
                    "status": "closed",
                    "reason": "",
                    "opentm": 1688592012.2317,
                    "closetm": 1688082549.3138,
                    "starttm": 0,
                    "expiretm": 0,
                    "descr": {
                        "pair": "XBTUSD",
                        "type": "buy",
                        "ordertype": "market",
                        "price": "0",
                        "price2": "0",
                        "leverage": "none",
                        "order": "sell 0.25000000 XBTUSD @ market",
                        "close": "",
                    },
                    "vol": "0.98000000",
                    "vol_exec": "0.98000000",
                    "cost": "7500.0",
                    "fee": "7.5",
                    "price": "27732.0",
                    "stopprice": "0.00000",
                    "limitprice": "0.00000",
                    "misc": "",
                    "oflags": "fcib",
                    "trades": ["TJUW2K-FLX2N-AR2FLU"],
                },
            },
        }
        self.fills = list[Trade]()
        self.execution_service.order_fill_event.connect(self.on_fill)

    async def asyncTearDown(self):
        pass

    def on_fill(self, _: str, trade: Trade):
        self.fills.append(trade)

    async def test_execution_boundary_refuses_an_order_while_unready(self):
        self.execution_service.health.mark_critical()
        self.execution_service.send_order = MagicMock()

        self.execution_service.on_order(self, self.mock_order)

        self.execution_service.send_order.assert_not_called()

    async def test_on_create_order(self):
        with patch.object(
            self.execution_service._client, "send_request"
        ) as request:
            request.return_value = self.response(self.create_order_response)
            self.execution_service.on_order(self, self.mock_order)
            request.assert_called_once()
            self.assertEqual(
                self.mock_order, self.execution_service.order_history["123"]
            )
            request.side_effect = self.execution_responses(
                self.closed_orders_response
            )
            await asyncio.sleep(self.execution_service._poll_interval + 0.01)

        self.assertEqual(2, len(self.fills))
        by_id = {fill.exchange_execution_id: fill for fill in self.fills}
        for order_id, details in self.closed_orders_response["result"].items():
            exchange_execution_id = details["trades"][0]
            fill = by_id[exchange_execution_id]
            self.assertEqual(
                unique_trade_id("Kraken", order_id, exchange_execution_id),
                fill.unique_trade_id,
            )
            self.assertEqual("123", fill.client_order_id)
            self.assertEqual("Kraken", fill.exchange)
            self.assertEqual(order_id, fill.exchange_order_id)
            self.assertEqual("BTC-USD", fill.symbol)
            self.assertEqual(MarketSide.BUY, fill.side)
            self.assertEqual(float(details["price"]), fill.price)
            self.assertEqual(float(details["fee"]), fill.fee)
            self.assertEqual(float(details["vol_exec"]), fill.quantity)
            self.assertEqual(
                datetime.fromtimestamp(details["closetm"], tz=pytz.utc),
                fill.transaction_time,
            )

    @staticmethod
    def response(payload):
        return MagicMock(status_code=200, json=MagicMock(return_value=payload))

    def execution_responses(self, orders):
        trades = {
            execution_id: {
                "ordertxid": order_id,
                "trade_id": 12345,
                "type": details["descr"]["type"],
                "price": details["price"],
                "fee": details["fee"],
                "vol": details["vol_exec"],
                "time": details["closetm"],
            }
            for order_id, details in orders["result"].items()
            for execution_id in details.get("trades", [])
        }
        return [
            self.response(orders),
            self.response({"error": [], "result": trades}),
        ]

    async def test_on_cancel_order(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "error": [],
                "result": {"count": 1},
            }

            self.execution_service.on_cancel_order(
                self, CancelOrder(client_order_id="123")
            )

            mock_post.assert_called_once()
            sent_data = mock_post.call_args.kwargs["data"]
            self.assertEqual(123, sent_data["txid"])
            self.assertNotIn(
                self.execution_service.ErrorCode.CANCEL_ORDER_FAILURE.name,
                [issue.message for issue in self.execution_service._issues],
            )

    async def test_on_cancel_order_fail(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "error": ["EOrder:Unknown order"],
            }

            self.execution_service.on_cancel_order(
                self, CancelOrder(client_order_id="123")
            )

            self.assertIn(
                self.execution_service.ErrorCode.CANCEL_ORDER_FAILURE.name,
                [issue.message for issue in self.execution_service._issues],
            )

    async def test_on_cancel_order_raises_exception(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            # A non-numeric client_order_id can't be encoded as the
            # numeric `userref`/`txid` Kraken expects, so send_cancel_order
            # raises before any request is made.
            self.execution_service.on_cancel_order(
                self, CancelOrder(client_order_id="not-a-number")
            )

            mock_post.assert_not_called()
            self.assertIn(
                self.execution_service.ErrorCode.CANCEL_ORDER_FAILURE.name,
                [issue.message for issue in self.execution_service._issues],
            )

    async def test_poll_trades_fail(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = (
                self.create_order_response
            )

            # Act
            self.execution_service.on_order(self, self.mock_order)

        with patch("requests.post", new_callable=MagicMock) as mock_post:
            tiny_time_advance = 1e-10

            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 400
            mock_post.return_value.json.return_value = {}

            for i in range(0, 6):
                # When get fills fail, it will automatically send another poll
                # request after _poll_interval second
                mock_post.reset_mock()
                await asyncio.sleep(self.execution_service._poll_interval)
                mock_post.assert_called_once()

            mock_post.reset_mock()
            await asyncio.sleep(tiny_time_advance)
            mock_post.assert_not_called()

    def order_status_response(self, *statuses: tuple[str, str]):
        """A QueryOrders response, one entry per (status, vol_exec)."""
        return {
            "error": [],
            "result": {
                f"TXID-{i}": {
                    "status": status,
                    "trades": [f"TRADE-{i}"] if float(vol_exec) else [],
                    "closetm": 1688667796.8802,
                    "descr": {
                        "pair": "XBTUSD",
                        "type": "buy",
                        "ordertype": "market",
                    },
                    "vol": vol_exec,
                    "vol_exec": vol_exec,
                    "fee": "1.0",
                    "price": "30010.0",
                }
                for i, (status, vol_exec) in enumerate(statuses)
            },
        }

    async def test_on_order_rejected_by_exchange(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "error": ["EOrder:Insufficient funds"],
            }

            self.execution_service.on_order(self, self.mock_order)

        self.assertIn(
            self.execution_service.ErrorCode.CREATE_ORDER_FAILURE.name,
            [issue.message for issue in self.execution_service._issues],
        )
        self.assertEqual({}, self.execution_service.order_history)

    async def test_on_order_raises_before_reaching_the_exchange(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            # A non-numeric client_order_id can't be encoded as the numeric
            # `userref` Kraken expects, so send_order raises before any
            # request is made.
            self.execution_service.on_order(
                self,
                Order(
                    client_order_id="not-a-number",
                    order_type=OrderType.MARKET_ORDER,
                    symbol="BTC-USD",
                    side=MarketSide.BUY,
                    price=100,
                    quantity=1,
                    creation_time=datetime(2024, 1, 1, 0, 0, 0),
                ),
            )

            mock_post.assert_not_called()

        self.assertIn(
            self.execution_service.ErrorCode.CREATE_ORDER_FAILURE.name,
            [issue.message for issue in self.execution_service._issues],
        )
        self.assertEqual({}, self.execution_service.order_history)

    async def test_response_without_a_transaction_id_is_not_polled(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "error": [],
                "result": {"descr": {"order": "buy 1.0 XBTUSD @ market"}},
            }

            self.execution_service.on_order(self, self.mock_order)
            mock_post.reset_mock()

            await asyncio.sleep(self.execution_service._poll_interval + 0.01)

            mock_post.assert_not_called()
            self.assertEqual([], self.fills)

    async def test_open_order_without_executions_has_no_fills(self):
        orders = self.order_status_response(("open", "0"))
        with patch.object(
            self.execution_service._client,
            "send_request",
            return_value=self.response(orders),
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "still open"):
                self.execution_service._get_fills(["TXID-0"], self.mock_order)
        request.assert_called_once()
        self.assertEqual([], self.fills)

    async def test_partial_fill_is_reported_once_while_polling_continues(self):
        orders = self.order_status_response(("open", "0.3"))
        responses = self.execution_responses(orders) + [self.response(orders)]
        with patch.object(
            self.execution_service._client,
            "send_request",
            side_effect=responses,
        ) as request:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "still open"):
                    self.execution_service._get_fills(
                        ["TXID-0"], self.mock_order
                    )
        self.assertEqual(3, request.call_count)
        self.assertEqual([0.3], [fill.quantity for fill in self.fills])

    async def test_canceled_partial_order_finishes_without_reemitting_fill(
        self,
    ):
        orders = self.order_status_response(("open", "0.3"))
        with patch.object(
            self.execution_service._client,
            "send_request",
            side_effect=self.execution_responses(orders),
        ):
            with self.assertRaisesRegex(RuntimeError, "still open"):
                self.execution_service._get_fills(["TXID-0"], self.mock_order)
        orders["result"]["TXID-0"]["status"] = "canceled"
        with patch.object(
            self.execution_service._client,
            "send_request",
            return_value=self.response(orders),
        ):
            self.execution_service._get_fills(["TXID-0"], self.mock_order)
        self.assertEqual(1, len(self.fills))
