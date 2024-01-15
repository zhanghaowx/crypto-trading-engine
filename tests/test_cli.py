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
        "market_data.coinbase.public_feed.PublicFeed.connect"
    )
    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.historical_feed.HistoricalFeed.connect"
    )
    async def test_main_run_once_mode(
        self,
        mock_public_feed_connect,
        mock_historical_feed_connect,
    ):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Call the main function
        from crypto_trading_engine.cli import main

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        output = captured_output.getvalue().split("\n")
        self.assertLessEqual(1, len(output))
        self.assertEqual(output[0], "")

    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.public_feed.PublicFeed.connect"
    )
    @patch(
        "crypto_trading_engine."
        "market_data.coinbase.historical_feed.HistoricalFeed.connect"
    )
    async def test_main_training_mode(
        self,
        mock_public_feed_connect,
        mock_historical_feed_connect,
    ):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Call the main function
        from crypto_trading_engine.cli import main

        await main(training_mode=True)

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        output = captured_output.getvalue().split("\n")
        self.assertLessEqual(1, len(output))
        self.assertEqual(output[0], "")

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
