import argparse
import sys
import unittest
from io import StringIO
from unittest.mock import patch, AsyncMock


class TestCryptoTradingEngineTraining(unittest.IsolatedAsyncioTestCase):
    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            train_db="",
            exchange="Kraken",
        ),
    )
    @patch("asyncio.sleep", return_value=None)
    async def test_main_training_mode_with_kraken(
        self,
        mock_sleep,
        mock_args,
        MockApplication,
    ):
        mock_app = MockApplication.return_value
        mock_app.run_local_replay = AsyncMock()
        mock_app.run_local_replay.return_value = 1.0

        # Call the main function
        from jolteon.train import train

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await train()

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        self.assertLess(1, mock_app.run_local_replay.call_count)
        self.assertEqual(captured_output.getvalue().split("\n")[-1], "")

    @patch("jolteon.app.coinbase.CoinbaseApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            train_db="",
            exchange="Coinbase",
        ),
    )
    @patch("asyncio.sleep", return_value=None)
    async def test_main_training_mode_with_coinbase(
        self,
        mock_sleep,
        mock_args,
        MockApplication,
    ):
        mock_app = MockApplication.return_value
        mock_app.run_local_replay = AsyncMock()
        mock_app.run_local_replay.return_value = 1.0

        # Call the main function
        from jolteon.train import train

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await train()

        # Reset stdout
        sys.stdout = sys.__stdout__

        # Add assertions based on your expectations
        # For example, check if the connect methods were called
        self.assertLess(1, mock_app.run_local_replay.call_count)
        self.assertEqual(captured_output.getvalue().split("\n")[-1], "")
