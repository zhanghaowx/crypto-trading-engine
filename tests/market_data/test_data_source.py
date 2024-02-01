import unittest
from datetime import datetime
from unittest.mock import patch, Mock

import pandas as pd

from jolteon.core.side import MarketSide
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.data_source import DatabaseDataSource


class TestDatabaseDataSource(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create an instance of DatabaseDataSource
        self.database_data_source = DatabaseDataSource(database_name="test.db")

        # Define the expected Trade objects
        self.sql_result = pd.DataFrame(
            {
                "trade_id": [1, 2],
                "client_order_id": ["client1", "client2"],
                "symbol": ["BTC/USD", "ETH/USD"],
                "maker_order_id": ["maker1", "maker2"],
                "taker_order_id": ["taker1", "taker2"],
                "side": ["buy", "sell"],
                "price": [100.0, 200.0],
                "fee": [0.0, 0.0],
                "quantity": [1.0, 2.0],
                "transaction_time": [
                    1641031200,
                    1641031200,
                ],
            }
        )
        self.transaction_time = datetime.fromisoformat("2022-01-01T10:00:00Z")
        self.expected_trades = [
            Trade(
                trade_id=1,
                client_order_id="client1",
                symbol="BTC/USD",
                maker_order_id="maker1",
                taker_order_id="taker1",
                side=MarketSide.BUY,
                price=100.0,
                fee=0.0,
                quantity=1.0,
                transaction_time=self.transaction_time,
            ),
            Trade(
                trade_id=2,
                client_order_id="client2",
                symbol="ETH/USD",
                maker_order_id="maker2",
                taker_order_id="taker2",
                side=MarketSide.SELL,
                price=200.0,
                fee=0.0,
                quantity=2.0,
                transaction_time=self.transaction_time,
            ),
        ]

    @patch("sqlite3.connect")
    @patch("pandas.read_sql")
    async def test_download_market_trades(self, mock_read_sql, mock_connect):
        # Mock the database connection and read_sql function
        mock_connect.return_value = Mock()
        mock_read_sql.return_value = self.sql_result

        # Call the method to test
        result = await self.database_data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=datetime(2022, 1, 1, 0, 0, 0),
            end_time=datetime(2022, 1, 2, 0, 0, 0),
        )

        # Assert that the expected trades match the actual result
        self.assertEqual(result, self.expected_trades)

        # Assert that the database connection and read_sql function were called
        mock_connect.assert_called_once_with("test.db")
        mock_read_sql.assert_called_once_with(
            f"select * from {Events().market_trade.name}",
            con=mock_connect.return_value,
        )

    @patch("sqlite3.connect")
    @patch("pandas.read_sql")
    async def test_get_start_time(self, mock_read_sql, mock_connect):
        # Mock the database connection and read_sql function
        mock_connect.return_value = Mock()
        mock_read_sql.return_value = self.sql_result

        # Assert that the expected trades match the actual result
        self.assertEqual(
            self.database_data_source.start_time(),
            self.transaction_time,
        )

        # Assert that the database connection and read_sql function were called
        mock_connect.assert_called_once_with("test.db")
        mock_read_sql.assert_called_once_with(
            f"select * from {Events().market_trade.name} "
            f"order by transaction_time asc limit 1",
            con=mock_connect.return_value,
        )

    @patch("sqlite3.connect")
    @patch("pandas.read_sql")
    async def test_get_end_time(self, mock_read_sql, mock_connect):
        # Mock the database connection and read_sql function
        mock_connect.return_value = Mock()
        mock_read_sql.return_value = self.sql_result

        self.assertEqual(
            self.database_data_source.end_time(),
            self.transaction_time,
        )

        # Assert that the database connection and read_sql function were called
        mock_connect.assert_called_once_with("test.db")
        mock_read_sql.assert_called_once_with(
            f"select * from {Events().market_trade.name} "
            f"order by transaction_time desc limit 1",
            con=mock_connect.return_value,
        )
