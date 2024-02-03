import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytz

from jolteon.market_data.core.trade import Trade
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)


class TestApplication(unittest.IsolatedAsyncioTestCase):
    @patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
    @patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
    async def asyncSetUp(self):
        self.symbol = "ETH-USD"
        self.mock_connector = MagicMock()
        self.mock_md_live = MagicMock()
        self.mock_md_historical = MagicMock()
        self.mock_strategy = MagicMock()
        self.mock_exec_service = MagicMock()
        self.mock_position_manager = MagicMock()

        from jolteon.app.coinbase import CoinbaseApplication

        CoinbaseApplication.THREAD_SYNC_INTERVAL = 0.01

        self.application = CoinbaseApplication(
            symbol=self.symbol,
            database_name=f"{tempfile.gettempdir()}/unittest.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/unittest.log",
            strategy_params=StrategyParameters(),
        )

        self.application._signal_connector = self.mock_connector
        self.application._md_live = self.mock_md_live
        self.application._md_historical = self.mock_md_historical
        self.application._strategy = self.mock_strategy
        self.application._exec_service = self.mock_exec_service
        self.application._position_manager = self.mock_position_manager

    @patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
    @patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
    @patch("jolteon.app.coinbase.HistoricalFeed")
    async def test_run_replay(self, MockFeed):
        MockFeed.__name__ = "MockFeed"
        mock_feed = MockFeed.return_value
        mock_feed.connect = AsyncMock()

        start_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=0, tzinfo=pytz.utc
        )
        end_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=1, tzinfo=pytz.utc
        )

        # Mock the historical feed connection
        await self.application.run_replay(start_time, end_time)

        # Ensure the historical feed connection is called with the correct
        # arguments
        mock_feed.connect.assert_called_once_with(
            self.symbol, start_time, end_time
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

    @patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
    @patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
    @patch("jolteon.app.coinbase.PublicFeed")
    async def test_run(self, MockFeed):
        MockFeed.__name__ = "MockFeed"
        mock_feed = MockFeed.return_value
        mock_feed.connect = AsyncMock()

        # Mock the live feed connection
        await self.application.start()

        # Ensure the live feed connection is called with the correct arguments
        mock_feed.connect.assert_called_once_with(self.symbol)
