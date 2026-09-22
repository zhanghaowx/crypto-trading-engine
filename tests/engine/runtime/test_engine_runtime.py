import logging
import sqlite3
import tempfile
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.logging.logger import SQLiteHandler
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
    parameter_service,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.runtime.engine_runtime import EngineRuntime
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    IFairPriceModel,
)


class SubscribingFairPriceModel(IFairPriceModel, SignalSubscriber):
    """A minimal stand-in for AdjustedFairPriceModel: an IFairPriceModel
    that is also a SignalSubscriber, to check connect_all() discovers
    it."""

    def __init__(self):
        super().__init__()
        self.ticks_seen = 0

    def _calculate(self, context: BookSnapshot) -> FairPrice:
        return FairPrice(bid=0.0, ask=0.0)

    @subscribe("bbo_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.ticks_seen += 1


class _Venue(SignalSubscriber):
    def __init__(self):
        self.latest_bbo: BBO | None = None

    @subscribe("bbo_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.latest_bbo = bbo


class TestEngineRuntimeDisconnect(unittest.TestCase):
    def _make_app(self, name: str, venue: _Venue):
        app = EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_{name}.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_{name}.log",
        )
        return app.use_execution_service(venue)

    def test_stopping_one_app_leaves_another_apps_subscribers_connected(self):
        stopped_venue, running_venue = _Venue(), _Venue()
        stopped = self._make_app("stopped", stopped_venue)
        running = self._make_app("running", running_venue)
        stopped.connect_all()
        running.connect_all()

        stopped.disconnect_all()
        tick = BBO(
            symbol="BTC/USD",
            bid_price=100.0,
            bid_quantity=1.0,
            ask_price=102.0,
            ask_quantity=1.0,
        )
        signal("bbo_feed").send("mock_sender", bbo=tick)

        self.assertIsNone(stopped_venue.latest_bbo)
        self.assertEqual(tick, running_venue.latest_bbo)
        running.disconnect_all()


class TestEngineRuntimeEngineRun(unittest.TestCase):
    def setUp(self):
        self._apps: list[EngineRuntime] = []

    def tearDown(self):
        self._release_files()

    def _release_files(self):
        # Windows will not delete the temporary directory while anything
        # still holds one of its files open, and each application leaves
        # two writers behind: its recorder, and the SQLite log handler
        # setup_global_logger installed on the root logger.
        for app in self._apps:
            app._signal_recorder.close()
        self._apps.clear()

        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, SQLiteHandler):
                root_logger.removeHandler(handler)
                handler.close()

    def _make_app(self, folder: str, name: str) -> EngineRuntime:
        app = EngineRuntime(
            symbol="BTC/USD",
            exchange="Binance.US",
            database_name=f"{folder}/{name}.sqlite",
            logfile_name=f"{folder}/{name}.log",
        )
        self._apps.append(app)
        return app

    def test_each_application_gets_a_unique_run_id(self):
        with tempfile.TemporaryDirectory() as folder:
            first = self._make_app(folder, "first")
            second = self._make_app(folder, "second")

            self.assertNotEqual(
                first._engine_run.run_id, second._engine_run.run_id
            )
            self._release_files()

    def test_graceful_stop_records_the_run_end(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self._make_app(folder, "recorded")
            run_id = app._engine_run.run_id
            app._connect_signals()
            app.stop()
            self._release_files()

            with closing(sqlite3.connect(f"{folder}/recorded.sqlite")) as conn:
                rows = conn.execute(
                    "SELECT run_id, exchange, symbol, started_at, ended_at "
                    "FROM engine_run"
                ).fetchall()

        self.assertEqual(1, len(rows))
        recorded = rows[0]
        self.assertEqual(run_id, recorded[0])
        self.assertEqual("Binance.US", recorded[1])
        self.assertEqual("BTC/USD", recorded[2])
        self.assertIsNotNone(recorded[3])
        self.assertIsNotNone(recorded[4])


class TestEngineRuntimeFairPriceModel(unittest.TestCase):
    def _make_app(self, fair_price_model):
        return EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_base.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_base.log",
            fair_price_model=fair_price_model,
        )

    def test_connect_all_wires_a_subscribing_fair_price_model(self):
        model = SubscribingFairPriceModel()
        app = self._make_app(model)

        app.connect_all()
        signal("bbo_feed").send(
            "mock_sender",
            bbo=BBO(
                symbol="BTC/USD",
                bid_price=100.0,
                bid_quantity=1.0,
                ask_price=102.0,
                ask_quantity=1.0,
            ),
        )

        self.assertEqual(1, model.ticks_seen)
        app.disconnect_all()

    def test_connect_all_tolerates_a_non_subscribing_fair_price_model(self):
        app = self._make_app(fair_price_model=None)

        app.connect_all()
        app.disconnect_all()

    def test_uses_the_health_monitor_shared_by_constructed_services(self):
        health_monitor = HealthMonitor()
        parameters = StaticParameterService(health_monitor=health_monitor)
        app = EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_ready.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_ready.log",
            parameter_service=parameters,
            health_monitor=health_monitor,
        )

        self.assertIs(health_monitor, app._health_monitor)
        self.assertEqual(HealthState.INITIALIZING, app._health_monitor.state)
        parameters.start()
        self.assertEqual(HealthState.HEALTHY, app._health_monitor.state)


class TestEngineRuntimeRunStart(unittest.IsolatedAsyncioTestCase):
    def _make_app(self):
        return EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_run_start.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_run_start.log",
        )

    async def test_run_start_without_a_market_data_thread(self):
        """
        Replays run the feed inline so a test (or a profiler) sees the whole
        run on one thread.
        """
        app = self._make_app()
        connected = []

        async def connect(symbol, *args):
            connected.append((symbol, args))

        app.use_market_data_service(SimpleNamespace(connect=connect))

        with patch.object(EngineRuntime, "THREAD_ENABLED", False):
            pnl = await app.run_start()

        self.assertEqual([("BTC/USD", ())], connected)
        self.assertEqual(0.0, pnl)

    async def test_market_data_thread_reports_an_unexpected_failure(self):
        """
        The feed runs on a thread of its own, so a failure there has no
        caller to propagate to and would otherwise be lost.
        """

        async def failing_connect():
            raise RuntimeError("feed blew up")

        with (
            patch("threading.excepthook"),
            self.assertLogs(level="ERROR") as logs,
        ):
            thread, _, _ = EngineRuntime._start_thread("MD", failing_connect())
            thread.join(timeout=5)

        self.assertIn("MD got exception: feed blew up", "".join(logs.output))


if __name__ == "__main__":
    unittest.main()


class TestEngineRuntimeParameterService(unittest.IsolatedAsyncioTestCase):
    def _make_app(self, parameter_service=None):
        return EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_parameters.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_parameters.log",
            parameter_service=parameter_service,
        )

    def test_publishes_the_service_the_layers_underneath_read(self):
        service = StaticParameterService()
        self._make_app(service)
        self.assertIs(service, parameter_service())

    async def test_polls_only_while_the_engine_is_running(self):
        service = _RecordingParameterService()
        app = self._make_app(service)

        async def connect(symbol, *args):
            self.assertEqual(1, service.started)
            self.assertEqual(0, service.stopped)

        app.use_market_data_service(SimpleNamespace(connect=connect))
        with patch.object(EngineRuntime, "THREAD_ENABLED", False):
            await app.run_start()

        self.assertEqual(1, service.stopped)

    async def test_stops_polling_even_when_the_feed_fails(self):
        service = _RecordingParameterService()
        app = self._make_app(service)

        async def connect(symbol, *args):
            raise RuntimeError("feed blew up")

        app.use_market_data_service(SimpleNamespace(connect=connect))
        with patch.object(EngineRuntime, "THREAD_ENABLED", False):
            with self.assertRaises(RuntimeError):
                await app.run_start()

        self.assertEqual(1, service.stopped)


class _RecordingParameterService(StaticParameterService):
    def __init__(self):
        super().__init__()
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1
