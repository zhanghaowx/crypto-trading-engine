import os
import signal
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from io import StringIO


@patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
@patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
class TestCryptoTradingEngineCLI(unittest.IsolatedAsyncioTestCase):
    @patch(
        "crypto_trading_engine."
        "core.eventing.signal_connector.SignalConnector"
    )
    @patch(
        "crypto_trading_engine."
        "core.eventing.signal_connector.SignalConnector.connect"
    )
    @patch(
        "crypto_trading_engine." "strategy.bull_flag_strategy.BullFlagStrategy"
    )
    @patch(
        "crypto_trading_engine."
        "execution.coinbase.execution_service.MockExecutionService"
    )
    @patch(
        "crypto_trading_engine." "position.position_manager.PositionManager"
    )
    @patch(
        "crypto_trading_engine." "market_data.coinbase.public_feed.PublicFeed"
    )
    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.historical_feed.HistoricalFeed"
    )
    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.public_feed.PublicFeed.connect"
    )
    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.historical_feed.HistoricalFeed.connect"
    )
    async def test_main(
        self,
        mock_signal_connector,
        mock_public_feed,
        mock_historical_feed,
        mock_bull_flag_strategy,
        mock_execution_service,
        mock_position_manager,
        mock_signal_connector_connect,
        mock_public_feed_connect,
        mock_historical_feed_connect,
    ):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Mock the necessary objects
        mock_signal_connector.return_value = MagicMock()
        mock_public_feed.return_value = MagicMock()
        mock_historical_feed.return_value = MagicMock()
        mock_bull_flag_strategy.return_value = MagicMock()
        mock_execution_service.return_value = MagicMock()
        mock_position_manager.return_value = MagicMock()

        # Mock the connect methods
        mock_signal_connector_connect.return_value = MagicMock()
        mock_public_feed_connect.return_value = AsyncMock()
        mock_historical_feed_connect.return_value = AsyncMock()

        # Call the main function
        from crypto_trading_engine.cli import main

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called

    async def test_graceful_exit(self):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Mock sys.exit to prevent actual exit
        with patch("sys.exit") as mock_exit:
            from crypto_trading_engine.cli import graceful_exit

            graceful_exit(signal.SIGINT, None)

            # Reset stdout
            sys.stdout = sys.__stdout__

            self.assertEqual(
                "Ctrl+C detected. Performing graceful exit...\n",
                captured_output.getvalue(),
            )
            self.assertEqual(1, mock_exit.call_count)
