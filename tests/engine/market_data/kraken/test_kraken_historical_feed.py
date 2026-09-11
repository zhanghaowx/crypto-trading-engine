import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.data_source import IDataSource
from jolteon.engine.market_data.historical_feed import HistoricalFeed
from jolteon.engine.market_data.kraken.data_source import (
    KrakenHistoricalDataSource,
)


class TestHistoricalFeed(unittest.IsolatedAsyncioTestCase):
    def on_market_trade(self, _: str, market_trade: Trade):
        self.market_trades.append(market_trade)

    async def asyncSetUp(self):
        self.market_trades = []
        self.historical_feed = HistoricalFeed(
            data_source=KrakenHistoricalDataSource()
        )
        self.historical_feed.events.market_trade.connect(self.on_market_trade)

    async def test_connect_replays_trades(self):
        self.assertEqual(len(self.market_trades), 0)

        # Set up test parameters
        symbol = "BTC/USD"
        start_time = datetime(2023, 1, 1, 1, 1, 0, tzinfo=timezone.utc)
        end_time = datetime(2023, 1, 1, 1, 2, 0, tzinfo=timezone.utc)

        # Mock the requests.get method to return a custom JSON response
        mock_response = {
            "error": [],
            "result": {
                symbol: [
                    [50000.0, 1.0, start_time.timestamp(), "b", "m", "", 1],
                    [51000.0, 1.0, end_time.timestamp(), "s", "l", "", 2],
                    # Add more simulated trades as needed
                ],
                "last": end_time.timestamp() * 1e9,  # Mock the last timestamp
            },
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            # Set the return value of the mock to the custom JSON response
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            # Connect and simulate the asynchronous event loop
            await self.historical_feed.connect(symbol, start_time, end_time)

        self.assertEqual(len(self.market_trades), 2)

    async def test_connect_with_empty_trades(self):
        time_manager().use_fake_time = MagicMock()
        IDataSource.TRADE_CACHE.clear()

        # Set up test parameters
        symbol = "BTC/USD"
        start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2023, 1, 2, tzinfo=timezone.utc)

        # Mock the requests.get method to return a custom JSON response
        mock_response = {
            "error": [],
            "result": {symbol: [], "last": datetime(2024, 1, 1).timestamp()},
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            # Set the return value of the mock to the custom JSON response
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            # Connect and simulate the asynchronous event loop
            await self.historical_feed.connect(symbol, start_time, end_time)

        # Verify mock time is set properly
        time_manager().use_fake_time.assert_called_once()

    async def test_response_with_last_timestamp_equals_request_timestamp(self):
        time_manager().use_fake_time = MagicMock()
        IDataSource.TRADE_CACHE.clear()

        # Set up test parameters
        symbol = "BTC/USD"
        start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)

        # Mock the requests.get method to return a custom JSON response
        mock_response = {
            "error": [],
            "result": {
                symbol: [
                    [50000.0, 1.0, start_time.timestamp(), "b", "m", "", 1]
                ],
                "last": start_time.timestamp() * 1e9,
            },
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            # Set the return value of the mock to the custom JSON response
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            # Connect and simulate the asynchronous event loop
            await self.historical_feed.connect(
                symbol, start_time, start_time + timedelta(seconds=1)
            )

        self.assertEqual(len(self.market_trades), 1)

    async def test_warns_when_trade_ids_are_not_contiguous(self):
        IDataSource.TRADE_CACHE.clear()

        symbol = "BTC/USD"
        start_time = datetime(2023, 1, 1, 1, 1, 0, tzinfo=timezone.utc)
        end_time = datetime(2023, 1, 1, 1, 2, 0, tzinfo=timezone.utc)

        mock_response = {
            "error": [],
            "result": {
                symbol: [
                    [50000.0, 1.0, start_time.timestamp(), "b", "m", "", 1],
                    [51000.0, 1.0, end_time.timestamp(), "s", "l", "", 9],
                ],
                "last": end_time.timestamp() * 1e9,
            },
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            with self.assertLogs(level="WARNING") as logs:
                await self.historical_feed.connect(
                    symbol, start_time, end_time
                )

        self.assertIn(
            "Some market trades might be missing!", "".join(logs.output)
        )
        self.assertEqual(len(self.market_trades), 2)


class TestKrakenHistoricalDataSource(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        IDataSource.TRADE_CACHE.clear()
        self.data_source = KrakenHistoricalDataSource()
        self.symbol = "BTC/USD"
        self.start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        self.end_time = self.start_time + timedelta(seconds=1)

    async def asyncTearDown(self):
        IDataSource.TRADE_CACHE.clear()

    async def download(self):
        return await self.data_source.download_market_trades(
            self.symbol, self.start_time, self.end_time
        )

    def mock_get(self, status_code: int = 200, json_response=None):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_response
        return patch("requests.get", return_value=response)

    async def test_downloaded_trades_are_cached(self):
        json_response = {
            "error": [],
            "result": {
                self.symbol: [
                    [
                        50000.0,
                        1.0,
                        self.start_time.timestamp(),
                        "b",
                        "m",
                        "",
                        1,
                    ]
                ],
                "last": self.end_time.timestamp() * 1e9,
            },
        }

        with self.mock_get(json_response=json_response) as mock_get:
            first = await self.download()
            second = await self.download()

        self.assertEqual(first, second)
        self.assertEqual(1, mock_get.call_count)

    async def test_raises_on_a_failed_http_request(self):
        with self.mock_get(status_code=503):
            with self.assertRaises(Exception) as context:
                await self.download()

        self.assertIn("HTTP 503", str(context.exception))

    async def test_raises_on_an_error_reported_by_the_exchange(self):
        json_response = {
            "error": ["EQuery:Unknown asset pair"],
            "result": None,
        }

        with self.mock_get(json_response=json_response):
            with self.assertRaises(Exception) as context:
                await self.download()

        self.assertIn("EQuery:Unknown asset pair", str(context.exception))
