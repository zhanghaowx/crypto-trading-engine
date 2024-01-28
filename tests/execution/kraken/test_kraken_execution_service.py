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

        self.execution_service = ExecutionService(
            dry_run=False, poll_interval=0.1
        )
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

            await asyncio.sleep(self.execution_service._poll_interval + 0.01)
            self.assertEqual(len(self.fills), 2)
            self.assertEqual(self.fills[0].trade_id, 0)
            self.assertEqual(self.fills[0].client_order_id, "123")
            self.assertEqual(self.fills[0].symbol, "BTC-USD")
            self.assertEqual(self.fills[0].maker_order_id, "")
            self.assertEqual(self.fills[0].taker_order_id, "")
            self.assertEqual(self.fills[0].side, MarketSide.BUY)
            self.assertEqual(self.fills[0].price, 30010.00000)
            self.assertEqual(self.fills[0].quantity, 0.02000000)
            self.assertEqual(
                self.fills[0].transaction_time,
                datetime.fromtimestamp(1688667796.8802, tz=pytz.utc),
            )
            self.assertEqual(self.fills[1].trade_id, 0)
            self.assertEqual(self.fills[1].client_order_id, "123")
            self.assertEqual(self.fills[1].symbol, "BTC-USD")
            self.assertEqual(self.fills[1].maker_order_id, "")
            self.assertEqual(self.fills[1].taker_order_id, "")
            self.assertEqual(self.fills[1].side, MarketSide.BUY)
            self.assertEqual(self.fills[1].price, 27732.00000)
            self.assertEqual(self.fills[1].quantity, 0.980000)
            self.assertEqual(
                self.fills[1].transaction_time,
                datetime.fromtimestamp(1688082549.3138, tz=pytz.utc),
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
