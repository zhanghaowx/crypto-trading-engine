import asyncio
import os
import tempfile
import threading
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytz

from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.position.position_manager import Position


class TestApplication(unittest.IsolatedAsyncioTestCase):
    @patch.dict(os.environ, {"KRAKEN_API_KEY": "api_key"})
    @patch.dict(os.environ, {"KRAKEN_API_SECRET": "api_secret"})
    async def asyncSetUp(self):
        self.symbol = "ETH/USD"
        self.mock_signal_recorder = MagicMock()
        self.mock_md_live = MagicMock()
        self.mock_md_historical = MagicMock()
        self.mock_strategy = MagicMock()
        self.mock_exec_service = MagicMock()

        from jolteon.app.kraken import KrakenApplication

        self.application = KrakenApplication(
            symbol=self.symbol,
            database_name=f"{tempfile.gettempdir()}/unittest.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/unittest.log",
        )
        self.application._signal_recorder = self.mock_signal_recorder
        self.application._md_live = self.mock_md_live
        self.application._md_historical = self.mock_md_historical
        self.application._strategy = self.mock_strategy
        self.application._exec_service = self.mock_exec_service

        self.set_local_position(self.symbol, 0.123)

    def create_mock_feed(self, MockFeed):
        MockFeed.__name__ = "MockFeed"
        mock_feed = MockFeed.return_value
        mock_feed.connect = AsyncMock()
        return mock_feed

    def set_local_position(self, symbol: str, volume: float):
        self.application._position_manager.positions[self.symbol] = Position(
            symbol=symbol,
            volume=volume,
            cash_value=1.0,
        )

    @patch("jolteon.app.base.DatabaseDataSource")
    async def test_run_local_replay(self, MockDatabaseDataSource):
        mock_data_source = MockDatabaseDataSource.return_value
        mock_data_source.start_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )
        mock_data_source.end_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )
        mock_data_source.download_market_trades = AsyncMock()
        mock_data_source.download_market_trades.return_value = list[Trade]()

        await self.application.run_local_replay("/tmp/unittest.sqlite")

        mock_data_source.download_market_trades.assert_called_once()

    @patch("jolteon.app.kraken.HistoricalFeed")
    async def test_run_replay(self, MockFeed):
        mock_feed = self.create_mock_feed(MockFeed)

        # Exec
        start_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=0, tzinfo=pytz.utc
        )
        end_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=1, tzinfo=pytz.utc
        )
        await self.application.run_replay(start_time, end_time)

        # Ensure the historical feed connection is called with the correct
        # arguments
        mock_feed.connect.assert_called_once_with(
            self.symbol, start_time, end_time
        )

    @patch("jolteon.app.kraken.PublicFeed")
    async def test_run(self, MockFeed):
        mock_feed = self.create_mock_feed(MockFeed)

        # Mock the live feed connection
        await self.application.start()

        # Ensure the live feed connection is called with the correct arguments
        mock_feed.connect.assert_called_once_with(self.symbol)

    @patch("jolteon.app.kraken.PublicFeed")
    async def test_request_shutdown_cancels_a_feed_that_never_finishes(
        self, MockFeed
    ):
        """
        A live feed's connect() runs until cancelled, so nothing but an
        explicit shutdown request ever ends it - this is what a Ctrl+C
        needs to reach in order to unblock start() instead of hanging.
        """
        mock_feed = self.create_mock_feed(MockFeed)
        connected = threading.Event()

        async def never_ending_connect(symbol):
            connected.set()
            await asyncio.Event().wait()

        mock_feed.connect = never_ending_connect

        start_task = asyncio.ensure_future(self.application.start())
        await asyncio.get_running_loop().run_in_executor(
            None, connected.wait, 1
        )
        self.assertTrue(connected.is_set())

        self.application.request_shutdown()

        await asyncio.wait_for(start_task, timeout=1)
