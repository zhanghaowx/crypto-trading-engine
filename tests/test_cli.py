import os
import signal
import sys
import unittest
from io import StringIO
from unittest.mock import patch


@patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
@patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
class TestCryptoTradingEngineCLI(unittest.IsolatedAsyncioTestCase):
    @patch("jolteon.app.Application.run_replay")
    async def test_main_run_once_mode(
        self,
        mock_run_replay,
    ):
        mock_run_replay.return_value = 1.0

        # Call the main function
        from jolteon.cli import main

        await main(training=False, replay=True)

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        self.assertEqual(1, mock_run_replay.call_count)

    @patch("jolteon.app.Application.run_replay")
    async def test_main_training_mode_with_best_parameters_found(
        self,
        mock_run_replay,
    ):
        mock_run_replay.return_value = 1.0

        # Call the main function
        from jolteon.cli import main

        await main(training=True, replay=True)

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        self.assertLess(1, mock_run_replay.call_count)

    @patch("jolteon.app.Application.run_replay")
    async def test_main_training_mode_with_no_best_parameters_found(
        self,
        mock_run_replay,
    ):
        mock_run_replay.return_value = -1.0

        # Call the main function
        from jolteon.cli import main

        await main(training=True, replay=True)

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        self.assertLess(1, mock_run_replay.call_count)

    async def test_graceful_exit(self):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Mock sys.exit to prevent actual exit
        with patch("sys.exit") as mock_exit:
            from jolteon.cli import graceful_exit

            graceful_exit(signal.SIGINT, None)

            # Reset stdout
            sys.stdout = sys.__stdout__

            self.assertEqual(
                "Ctrl+C detected. Performing graceful exit...\n",
                captured_output.getvalue(),
            )
            self.assertEqual(1, mock_exit.call_count)
