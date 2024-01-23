import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytz

from jolteon.core.time.time_manager import time_manager
from jolteon.position.position_manager import Position
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)


class TestApplication(unittest.IsolatedAsyncioTestCase):
    @patch.dict(os.environ, {"KRAKEN_API_KEY": "api_key"})
    @patch.dict(os.environ, {"KRAKEN_API_SECRET": "api_secret"})
    async def asyncSetUp(self):
        self.symbol = "ETH/USD"
        self.mock_connector = MagicMock()
        self.mock_md_live = MagicMock()
        self.mock_md_historical = MagicMock()
        self.mock_strategy = MagicMock()
        self.mock_exec_service = MagicMock()

        from jolteon.app.kraken import KrakenApplication

        KrakenApplication.THREAD_SYNC_INTERVAL = 0.01

        self.application = KrakenApplication(
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

    async def asyncTearDown(self):
        time_manager().force_reset()

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
