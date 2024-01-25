import argparse
import signal
import sys
import unittest
from io import StringIO
from unittest.mock import patch, AsyncMock

from jolteon.cli import main


class TestCryptoTradingEngineCLI(unittest.IsolatedAsyncioTestCase):
    @patch("jolteon.app.coinbase.CoinbaseApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            exchange="Coinbase",
        ),
    )
    async def test_main_run_once_mode(self, mock_args, MockApplication):
        mock_app = MockApplication.return_value
        mock_app.run_replay = AsyncMock()
        mock_app.run_replay.return_value = 1.0

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.run_replay.call_count)
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            exchange="Kraken",
        ),
    )
    async def test_main_run_once_mode(self, mock_args, MockApplication):
        mock_app = MockApplication.return_value
        mock_app.run_replay = AsyncMock()
        mock_app.run_replay.return_value = 1.0

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.run_replay.call_count)
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            exchange="Mock",
        ),
    )
    async def test_main_run_once_mode(self, mock_args, MockApplication):
        with self.assertRaises(NotImplementedError) as context:
            await main()

        self.assertEqual(
            str(context.exception),
            "Application is not implemented for market Mock",
        )

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
