import argparse
import signal
import sys
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytz

from jolteon.cli.engine import main
from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.inventory import (
    InventoryAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.momentum import (
    MomentumAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.order_flow_imbalance import (  # noqa: E501
    OrderFlowImbalanceAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    AdjustedFairPriceParameters,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.parameters import (
    QuoteOffsetParameters,
)
from jolteon.engine.strategy.market_making.quote_offset import (
    FeeAwareQuoteOffsetService,
)

# Sessions write under a directory of their own. These tests never let
# one run far enough to create it, but main() still builds every path
# from it.
ROOT = "/tmp/jolteon-cli-test"


class TestCryptoTradingEngineCLI(unittest.IsolatedAsyncioTestCase):
    @patch("jolteon.engine.runtime.venues.kraken.KrakenRuntime")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            replay_db="",
            exchange="Kraken",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db=None,
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
        # A replay's recording is named by its run id like any other run's;
        # what it replayed is written into the recording, not its name.
        run_id = MockApplication.call_args.kwargs["run_id"]
        self.assertEqual(
            Path(MockApplication.call_args.kwargs["database_name"]).parts[-3:],
            ("kraken", "BTC-USD", f"{run_id}.sqlite"),
        )
        self.assertEqual(
            Path(MockApplication.call_args.kwargs["logfile_name"]).parts[-3:],
            ("kraken", "BTC-USD", f"{run_id}.log"),
        )

    @patch("jolteon.engine.runtime.venues.kraken.KrakenRuntime")
    @patch("jolteon.cli.engine.DatabaseDataSource")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="/tmp/unittest.sqlite",
            exchange="Kraken",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db=None,
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
            "A runtime is not implemented for market Mock",
        )

    @patch("jolteon.engine.runtime.venues.kraken.KrakenRuntime")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Kraken",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db="",
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
        run_id = MockApplication.call_args.kwargs["run_id"]
        self.assertEqual(
            Path(MockApplication.call_args.kwargs["database_name"]).parts[-3:],
            ("kraken", "BTC-USD", f"{run_id}.sqlite"),
        )
        self.assertEqual(
            Path(MockApplication.call_args.kwargs["logfile_name"]).parts[-3:],
            ("kraken", "BTC-USD", f"{run_id}.log"),
        )

    @patch("jolteon.engine.runtime.venues.kraken.KrakenRuntime")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Kraken",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db="",
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
        self.assertEqual(3, len(fair_price_model._adjustments))
        self.assertIsInstance(
            fair_price_model._adjustments[0], MomentumAdjustment
        )
        self.assertIsInstance(
            fair_price_model._adjustments[1], OrderFlowImbalanceAdjustment
        )
        inventory_adjustment = fair_price_model._adjustments[2]
        self.assertIsInstance(inventory_adjustment, InventoryAdjustment)
        self.assertIs(fair_price_model, strategy._fair_price_model)

        offset_service = strategy._quote_offset_service
        self.assertIsInstance(offset_service, FeeAwareQuoteOffsetService)

        # Every component was handed the same service, so the edge a
        # quote demands, the clamp on the adjustments and the skew at a
        # full position stay one number rather than three that drift.
        parameters = strategy._parameter_service
        edge = parameters.get(QuoteOffsetParameters, strategy._symbol).edge
        clamp = parameters.get(
            AdjustedFairPriceParameters, strategy._symbol
        ).max_adjustment
        self.assertEqual(edge, clamp)

        max_inventory = strategy._inventory_limit.max_inventory
        self.assertAlmostEqual(
            clamp,
            inventory_adjustment._scale_for(strategy._symbol) * max_inventory,
        )

        self.assertEqual("", captured_output.getvalue().split("\n")[-1])

    @patch("jolteon.engine.runtime.venues.binance_us.BinanceUsRuntime")
    @patch(
        "jolteon.cli.engine.engine_run_id",
        return_value="20260926T100000Z-abcd1234",
    )
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="",
            replay_end="",
            replay_db="",
            exchange="Binance.US",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db="",
            paper=True,
        ),
    )
    async def test_main_runs_binance_us_paper(
        self, mock_args, mock_run_id, MockApplication
    ):
        mock_app = MockApplication.return_value
        mock_app.start = AsyncMock(return_value=1.0)

        await main()

        mock_app.start.assert_awaited_once()
        self.assertTrue(MockApplication.call_args.kwargs["use_mock_execution"])
        # One id, minted once from when the process started, names both of
        # the run's files and is the id the runtime records under.
        mock_run_id.assert_called_once()
        self.assertIsInstance(mock_run_id.call_args.args[0], datetime)
        kwargs = MockApplication.call_args.kwargs
        self.assertEqual("20260926T100000Z-abcd1234", kwargs["run_id"])
        self.assertEqual(
            Path(kwargs["database_name"]).parts[-3:],
            ("binance-us", "BTC-USD", "20260926T100000Z-abcd1234.sqlite"),
        )
        self.assertEqual(
            Path(kwargs["logfile_name"]).parts[-3:],
            ("binance-us", "BTC-USD", "20260926T100000Z-abcd1234.log"),
        )

    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            replay_start="2024-01-01T00:00:00",
            replay_end="2024-01-02T00:00:00",
            replay_db="/tmp/unittest.sqlite",
            exchange="Kraken",
            symbol="BTC-USD",
            root=str(ROOT),
            params_db=None,
        ),
    )
    async def test_main_rejects_a_replay_range_and_a_database(self, mock_args):
        """
        A recording carries its own start and end, so asking for both a
        range and a database leaves it ambiguous which one to replay.
        """
        with self.assertRaises(AssertionError):
            await main()

    async def test_graceful_exit(self):
        # Redirect stdout to capture output
        captured_output = StringIO()
        sys.stdout = captured_output

        # Mock sys.exit to prevent actual exit
        with patch("sys.exit") as mock_exit:
            from jolteon.cli.engine import graceful_exit

            graceful_exit(signal.SIGINT, None)

            # Reset stdout
            sys.stdout = sys.__stdout__

            self.assertEqual(
                "Ctrl+C detected. Performing graceful exit...\n",
                captured_output.getvalue(),
            )
            self.assertEqual(1, mock_exit.call_count)

    async def test_graceful_exit_cancels_the_active_runtime_instead_of_exiting(
        self,
    ):
        """
        Once a runtime is running, Ctrl+C must cancel its MD thread's task
        rather than calling sys.exit() - sys.exit() only unwinds the main
        thread and leaves a live feed's connect() (which runs until
        cancelled) stuck, hanging shutdown.
        """
        import jolteon.cli.engine as cli

        mock_runtime = MagicMock()
        with (
            patch.object(cli, "_active_runtime", mock_runtime),
            patch("sys.exit") as mock_exit,
        ):
            cli.graceful_exit(signal.SIGINT, None)

            mock_runtime.request_shutdown.assert_called_once()
            mock_exit.assert_not_called()
