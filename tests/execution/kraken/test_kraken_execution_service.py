import asyncio
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

import pytz

from jolteon.core.side import MarketSide
from jolteon.execution.kraken.execution_service import ExecutionService
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade


class TestExecutionService(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.execution_service = ExecutionService(dry_run=False)
        self.execution_service._order_client = Mock()
        self.execution_service._user_client = Mock()
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
                "txid": ["OU22CG-KLAF2-FWUDD7"],
            },
        }
        self.closed_orders_response = {
            "error": [],
            "result": {
                "closed": {
                    "O37652-RJWRT-IMO74O": {
                        "refid": "None",
                        "userref": 1,
                        "status": "canceled",
                        "reason": "User requested",
                        "opentm": 1688148493.7708,
                        "closetm": 1688148610.0482,
                        "starttm": 0,
                        "expiretm": 0,
                        "descr": {
                            "pair": "XBTGBP",
                            "type": "buy",
                            "ordertype": "stop-loss-limit",
                            "price": "23667.0",
                            "price2": "0",
                            "leverage": "none",
                            "order": "buy 0.00100000 XBTGBP @ limit 23667.0",
                            "close": "",
                        },
                        "vol": "0.00100000",
                        "vol_exec": "0.00000000",
                        "cost": "0.00000",
                        "fee": "0.00000",
                        "price": "0.00000",
                        "stopprice": "0.00000",
                        "limitprice": "0.00000",
                        "misc": "",
                        "oflags": "fciq",
                        "trigger": "index",
                    },
                    "O6YDQ5-LOMWU-37YKEE": {
                        "refid": "None",
                        "userref": 123,
                        "status": "traded",
                        "reason": "User requested",
                        "opentm": 1688148493.7708,
                        "closetm": 1688148610.0477,
                        "starttm": 0,
                        "expiretm": 0,
                        "descr": {
                            "pair": "XBTEUR",
                            "type": "buy",
                            "ordertype": "take-profit-limit",
                            "price": "27743.0",
                            "price2": "0",
                            "leverage": "none",
                            "order": "buy 0.00100000 XBTEUR @ limit 27743.0",
                            "close": "",
                        },
                        "vol": "0.00100000",
                        "vol_exec": "1.00000000",
                        "cost": "0.00000",
                        "fee": "0.00000",
                        "price": "1.23000",
                        "stopprice": "0.00000",
                        "limitprice": "0.00000",
                        "misc": "",
                        "oflags": "fciq",
                        "trigger": "index",
                    },
                },
                "count": 2,
            },
        }
        self.fills = list[Trade]()

    async def asyncTearDown(self):
        pass

    def on_fill(self, _: str, trade: Trade):
        self.fills.append(trade)

    async def test_on_create_order(self):
        self.execution_service.order_fill_event.connect(self.on_fill)
        order_client = self.execution_service._order_client
        user_client = self.execution_service._user_client

        order_client.return_value = self.create_order_response
        user_client.get_closed_orders.return_value = (
            self.closed_orders_response
        )

        # Act
        self.execution_service.on_order(self, self.mock_order)

        # Assert
        self.assertEqual(
            self.execution_service.order_history["123"], self.mock_order
        )
        order_client.create_order.assert_called_once()
        user_client.get_closed_orders.assert_not_called()

        await asyncio.sleep(0.01)

        user_client.get_closed_orders.assert_called_once()

        await asyncio.sleep(1.01)

        user_client.get_closed_orders.assert_called_once()

        self.assertEqual(len(self.fills), 1)
        self.assertEqual(self.fills[0].trade_id, 0)
        self.assertEqual(self.fills[0].client_order_id, "123")
        self.assertEqual(self.fills[0].price, 1.23)
        self.assertEqual(self.fills[0].symbol, "BTC-USD")
        self.assertEqual(self.fills[0].maker_order_id, "")
        self.assertEqual(self.fills[0].taker_order_id, "")
        self.assertEqual(self.fills[0].side, MarketSide.BUY)
        self.assertEqual(self.fills[0].price, 1.23)
        self.assertEqual(self.fills[0].quantity, 1.0)
        self.assertEqual(
            self.fills[0].transaction_time,
            datetime(2023, 6, 30, 18, 10, 10, tzinfo=pytz.utc),
        )
