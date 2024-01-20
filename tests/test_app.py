import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytz

from jolteon.core.time.time_manager import time_manager
from jolteon.strategy.bull_flag.parameters import (
    Parameters,
)


class TestApplication(unittest.IsolatedAsyncioTestCase):
    @patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
    @patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
    @patch.dict(os.environ, {"KRAKEN_API_KEY": "api_key"})
    @patch.dict(os.environ, {"KRAKEN_API_SECRET": "api_secret"})
    async def asyncSetUp(self):
        self.symbol = "ETH-USD"
        self.mock_connector = MagicMock()
        self.mock_md_live = MagicMock()
        self.mock_md_historical = MagicMock()
        self.mock_strategy = MagicMock()
        self.mock_exec_service = MagicMock()
        self.mock_position_manager = MagicMock()

        from jolteon.app import Application

        self.application = Application(
            symbol=self.symbol,
            database_name=f"{tempfile.gettempdir()}/unittest.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/unittest.log",
            strategy_params=Parameters(),
        )

        # Disconnect all signals before changing to mock implementation
        self.application.disconnect_signals()

        self.application._signal_connector = self.mock_connector
        self.application._md_live = self.mock_md_live
        self.application._md_historical = self.mock_md_historical
        self.application._strategy = self.mock_strategy
        self.application._exec_service = self.mock_exec_service
        self.application._position_manager = self.mock_position_manager

    async def asyncTearDown(self):
        time_manager().force_reset()

    async def test_initialization(self):
        self.assertEqual(self.application._symbol, self.symbol)
        self.assertEqual(
            self.application._signal_connector, self.mock_connector
        )
        self.assertEqual(self.application._md_live, self.mock_md_live)
        self.assertEqual(
            self.application._md_historical, self.mock_md_historical
        )
        self.assertEqual(self.application._strategy, self.mock_strategy)
        self.assertEqual(
            self.application._exec_service, self.mock_exec_service
        )
        self.assertEqual(
            self.application._position_manager, self.mock_position_manager
        )

    async def test_run_replay(self):
        start_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=0, tzinfo=pytz.utc
        )
        end_time = datetime(
            2023, 1, 1, hour=0, minute=0, second=1, tzinfo=pytz.utc
        )

        # Mock the historical feed connection
        self.mock_md_historical.connect = AsyncMock()
        await self.application.run_replay(start_time, end_time)

        # Ensure the historical feed connection is called with the correct
        # arguments
        self.mock_md_historical.connect.assert_called_once_with(
            self.symbol, start_time, end_time
        )

    async def test_run(self):
        # Mock the live feed connection
        self.mock_md_live.connect = AsyncMock()
        self.mock_connector.persist = AsyncMock()
        await self.application.run()

        # Ensure the live feed connection is called with the correct arguments
        self.mock_md_live.connect.assert_called_once_with([self.symbol])
