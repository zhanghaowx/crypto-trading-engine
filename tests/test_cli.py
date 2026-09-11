import argparse
import signal
import sys
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytz

from jolteon.cli import main
from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.momentum import (
    MomentumAdjustment,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)


class TestCryptoTradingEngineCLI(unittest.IsolatedAsyncioTestCase):
    @patch("jolteon.app.coinbase.CoinbaseApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            replay_db="",
            exchange="Coinbase",
        ),
    )
    async def test_main_run_coinbase_replay(self, mock_args, MockApplication):
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

    @patch("jolteon.app.coinbase.CoinbaseApplication")
    @patch("jolteon.cli.DatabaseDataSource")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="/tmp/unittest.sqlite",
            exchange="Coinbase",
        ),
    )
    async def test_main_run_coinbase_replay_2(
        self, mock_args, MockDatabaseDataSource, MockApplication
    ):
        mock_app = MockApplication.return_value
        mock_app.run_local_replay = AsyncMock()
        mock_app.run_local_replay.return_value = 1.0

        mock_data_source = MockDatabaseDataSource.return_value
        mock_data_source.start_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )
        mock_data_source.end_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.run_local_replay.call_count)
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            replay_db="",
            exchange="Kraken",
        ),
    )
    async def test_main_run_kraken_replay(self, mock_args, MockApplication):
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
    @patch("jolteon.cli.DatabaseDataSource")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="/tmp/unittest.sqlite",
            exchange="Kraken",
        ),
    )
    async def test_main_run_kraken_replay_2(
        self, mock_args, MockDatabaseDataSource, MockApplication
    ):
        mock_app = MockApplication.return_value
        mock_app.run_local_replay = AsyncMock()
        mock_app.run_local_replay.return_value = 1.0

        mock_data_source = MockDatabaseDataSource.return_value
        mock_data_source.start_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )
        mock_data_source.end_time.return_value = datetime(
            2024, 1, 1, tzinfo=pytz.utc
        )

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.run_local_replay.call_count)
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            replay_db="",
            exchange="Mock",
        ),
    )
    async def test_main_run_mock_exchange_replay(self, mock_args):
        with self.assertRaises(NotImplementedError) as context:
            await main()

        self.assertEqual(
            str(context.exception),
            "Application is not implemented for market Mock",
        )

    @patch("jolteon.app.coinbase.CoinbaseApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Coinbase",
            paper=False,
        ),
    )
    async def test_main_run_coinbase_live(self, mock_args, MockApplication):
        mock_app = MockApplication.return_value
        mock_app.start = AsyncMock()
        mock_app.start.return_value = 1.0

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.start.call_count)
        self.assertIsNone(MockApplication.call_args.kwargs["strategy"])
        self.assertFalse(
            MockApplication.call_args.kwargs["use_mock_execution"]
        )
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Kraken",
            paper=False,
        ),
    )
    async def test_main_run_kraken_live(self, mock_args, MockApplication):
        mock_app = MockApplication.return_value
        mock_app.start = AsyncMock()
        mock_app.start.return_value = 1.0

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.start.call_count)
        self.assertIsNone(MockApplication.call_args.kwargs["strategy"])
        self.assertFalse(
            MockApplication.call_args.kwargs["use_mock_execution"]
        )
        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.app.kraken.KrakenApplication")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Kraken",
            paper=True,
        ),
    )
    async def test_main_run_kraken_paper(self, mock_args, MockApplication):
        mock_app = MockApplication.return_value
        mock_app.start = AsyncMock()
        mock_app.start.return_value = 1.0

        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        await main()

        # Reset stdout
        sys.stdout = sys.__stdout__

        self.assertEqual(1, mock_app.start.call_count)
        self.assertTrue(MockApplication.call_args.kwargs["use_mock_execution"])
        strategy = MockApplication.call_args.kwargs["strategy"]
        self.assertIsInstance(strategy, MarketMakingStrategy)
        self.assertEqual("BTC/USD", strategy._symbol)

        fair_price_model = MockApplication.call_args.kwargs["fair_price_model"]
        self.assertIsInstance(fair_price_model, AdjustedFairPriceModel)
        self.assertIsInstance(fair_price_model._base, MidPriceFairPriceModel)
        self.assertEqual(1, len(fair_price_model._adjustments))
        self.assertIsInstance(
            fair_price_model._adjustments[0], MomentumAdjustment
        )
        self.assertIs(fair_price_model, strategy._fair_price_model)

        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

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

    async def test_graceful_exit_cancels_the_active_app_instead_of_exiting(
        self,
    ):
        """
        Once an app is running, Ctrl+C must cancel its MD thread's task
        rather than calling sys.exit() - sys.exit() only unwinds the main
        thread and leaves a live feed's connect() (which runs until
        cancelled) stuck, hanging shutdown.
        """
        import jolteon.cli as cli

        mock_app = MagicMock()
        with (
            patch.object(cli, "_active_app", mock_app),
            patch("sys.exit") as mock_exit,
        ):
            cli.graceful_exit(signal.SIGINT, None)

            mock_app.request_shutdown.assert_called_once()
            mock_exit.assert_not_called()
