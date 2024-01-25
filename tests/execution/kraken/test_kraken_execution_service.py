import asyncio
import os
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, MagicMock

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade


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
        from jolteon.execution.kraken.execution_service import ExecutionService

        self.execution_service = ExecutionService(dry_run=False)
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
        self.execution_service.order_fill_event.connect(self.on_fill)

    async def asyncTearDown(self):
        pass

    def on_fill(self, _: str, trade: Trade):
        self.fills.append(trade)

    async def test_on_create_order(self):
        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = (
                self.create_order_response
            )

            # Act
            self.execution_service.on_order(self, self.mock_order)

            # Assert
            mock_post.assert_called_once()
            self.assertEqual(1, len(self.execution_service.order_history))
            self.assertEqual(
                self.execution_service.order_history["123"], self.mock_order
            )

        with patch("requests.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = (
                self.closed_orders_response
            )

            await asyncio.sleep(1.01)
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
