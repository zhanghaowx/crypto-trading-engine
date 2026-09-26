import logging
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytz

from jolteon.engine.core.engine_run import ExecutionMode, MarketDataMode
from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.logging.logger import SQLiteHandler
from jolteon.engine.core.parameter.live_parameter_service import (
    LiveParameterService,
)
from jolteon.engine.core.parameter.parameter_service import (
    ALL_SYMBOLS,
    StaticParameterService,
    parameter_service,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
)
from jolteon.engine.core.secrets import looks_secret
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)
from jolteon.engine.execution.kraken.parameters import (
    KrakenExecutionParameters,
)
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.data_source import IDataSource
from jolteon.engine.market_data.replay_input import ReplayInput
from jolteon.engine.runtime.engine_runtime import EngineRuntime
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
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


class _ConfigurableExecution:
    execution_mode = ExecutionMode.REAL

    def __init__(self):
        self.parameters = None
        self.symbol = None

    def configure(self, parameters, symbol: str) -> None:
        self.parameters = parameters
        self.symbol = symbol

    def describe_simulation(self, symbol: str) -> None:
        return None


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

    def test_a_run_given_no_id_mints_one_from_its_start(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self._make_app(folder, "minted")

            self.assertRegex(
                app._engine_run.run_id, r"^\d{8}T\d{6}Z-[0-9a-f]{8}$"
            )
            self._release_files()

    def test_a_run_given_an_id_records_every_row_under_it(self):
        with tempfile.TemporaryDirectory() as folder:
            app = EngineRuntime(
                symbol="BTC/USD",
                exchange="Binance.US",
                database_name=f"{folder}/named.sqlite",
                logfile_name=f"{folder}/named.log",
                run_id="20260926T100000Z-abcd1234",
            )
            self._apps.append(app)
            app._connect_signals()
            app.stop()
            self._release_files()

            with closing(sqlite3.connect(f"{folder}/named.sqlite")) as conn:
                rows = conn.execute(
                    "SELECT run_id FROM engine_run "
                    "UNION SELECT run_id FROM session_metadata"
                ).fetchall()

        self.assertEqual([("20260926T100000Z-abcd1234",)], rows)

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


def _execution_service(mode: ExecutionMode) -> SimpleNamespace:
    return SimpleNamespace(execution_mode=mode)


def _market_data_feed(mode: MarketDataMode) -> SimpleNamespace:
    return SimpleNamespace(market_data_mode=mode)


class TestEngineRunClassification(unittest.TestCase):
    """The two modes a run is classified by, taken from what it was wired
    with rather than from the file it writes or whether it finished."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._app = EngineRuntime(
            symbol="BTC/USD",
            exchange="Binance.US",
            database_name=f"{self._folder.name}/modes.sqlite",
            logfile_name=f"{self._folder.name}/modes.log",
        )

    def tearDown(self):
        self._app._signal_recorder.close()
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, SQLiteHandler):
                root_logger.removeHandler(handler)
                handler.close()
        self._folder.cleanup()

    def _recorded_modes(self) -> list[tuple]:
        self._app._signal_recorder.flush()
        with closing(
            sqlite3.connect(f"{self._folder.name}/modes.sqlite")
        ) as conn:
            return conn.execute(
                "SELECT execution_mode, market_data_mode, ended_at "
                "FROM engine_run"
            ).fetchall()

    def test_live_paper_trading_is_simulated_off_a_live_feed(self):
        self._app.use_execution_service(
            _execution_service(ExecutionMode.SIMULATED)
        )
        self._app.use_market_data_service(
            _market_data_feed(MarketDataMode.REALTIME)
        )
        self._app._connect_signals()

        self.assertEqual(
            [("SIMULATED", "REALTIME", None)], self._recorded_modes()
        )

    def test_a_replay_is_simulated_off_a_recording(self):
        self._app.use_execution_service(
            _execution_service(ExecutionMode.SIMULATED)
        )
        self._app.use_market_data_service(
            _market_data_feed(MarketDataMode.RECORDED)
        )
        self._app._connect_signals()

        self.assertEqual(
            [("SIMULATED", "RECORDED", None)], self._recorded_modes()
        )

    def test_live_trading_is_real_execution_off_a_live_feed(self):
        self._app.use_execution_service(_execution_service(ExecutionMode.REAL))
        self._app.use_market_data_service(
            _market_data_feed(MarketDataMode.REALTIME)
        )
        self._app._connect_signals()

        self.assertEqual([("REAL", "REALTIME", None)], self._recorded_modes())

    def test_a_run_wired_with_neither_records_neither_mode(self):
        self._app._connect_signals()

        self.assertEqual(
            [("UNKNOWN", "UNKNOWN", None)], self._recorded_modes()
        )

    def test_stopping_records_an_end_without_changing_the_modes(self):
        self._app.use_execution_service(
            _execution_service(ExecutionMode.SIMULATED)
        )
        self._app.use_market_data_service(
            _market_data_feed(MarketDataMode.RECORDED)
        )
        self._app._connect_signals()
        self._app.stop()

        recorded = self._recorded_modes()
        self.assertEqual(1, len(recorded))
        self.assertEqual(("SIMULATED", "RECORDED"), recorded[0][:2])
        self.assertIsNotNone(recorded[0][2])


class _MeanReversionStrategy:
    pass


class TestEngineRunStrategy(unittest.TestCase):
    """Which strategy a run records: the class it was actually built
    with, and "" when it was built with none."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._apps: list[EngineRuntime] = []

    def tearDown(self):
        for app in self._apps:
            app._signal_recorder.close()
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, SQLiteHandler):
                root_logger.removeHandler(handler)
                handler.close()
        self._folder.cleanup()

    def _make_app(self, name: str, strategy: object) -> EngineRuntime:
        app = EngineRuntime(
            symbol="BTC/USD",
            exchange="Binance.US",
            database_name=f"{self._folder.name}/{name}.sqlite",
            logfile_name=f"{self._folder.name}/{name}.log",
            strategy=strategy,
        )
        self._apps.append(app)
        return app

    def _recorded_strategy(self, name: str) -> list[tuple]:
        with closing(
            sqlite3.connect(f"{self._folder.name}/{name}.sqlite")
        ) as conn:
            return conn.execute("SELECT strategy FROM engine_run").fetchall()

    def test_a_run_records_the_class_of_the_strategy_it_ran(self):
        app = self._make_app("trading", _MeanReversionStrategy())
        app._connect_signals()
        app._signal_recorder.flush()

        self.assertEqual(
            [("_MeanReversionStrategy",)], self._recorded_strategy("trading")
        )

    def test_a_run_built_with_no_strategy_records_none(self):
        app = self._make_app("recording", None)
        app._connect_signals()
        app._signal_recorder.flush()

        self.assertEqual([("",)], self._recorded_strategy("recording"))


class TestReplayInput(unittest.TestCase):
    """What a replay records about the data it read, kept apart from when
    the replay itself ran."""

    DATA_START = datetime(2024, 3, 1, 9, 0, tzinfo=pytz.utc)
    DATA_END = datetime(2024, 3, 1, 10, 0, tzinfo=pytz.utc)

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._app = EngineRuntime(
            symbol="BTC/USD",
            exchange="Binance.US",
            database_name=f"{self._folder.name}/replay.sqlite",
            logfile_name=f"{self._folder.name}/replay.log",
        )

    def tearDown(self):
        self._app._signal_recorder.close()
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, SQLiteHandler):
                root_logger.removeHandler(handler)
                handler.close()
        self._folder.cleanup()

    def _data_source(self, replay_input: ReplayInput) -> MagicMock:
        source = MagicMock(spec=IDataSource)
        source.describe_replay_input.return_value = replay_input
        return source

    def _recorded(self) -> dict:
        self._app._signal_recorder.flush()
        with closing(
            sqlite3.connect(f"{self._folder.name}/replay.sqlite")
        ) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM engine_run").fetchone()
        return dict(row)

    def test_a_replay_records_where_its_data_came_from(self):
        self._app.use_recorded_market_data(
            self._data_source(
                ReplayInput(
                    source="/recordings/live.sqlite",
                    source_run_id="20260920T100000Z-abc123",
                    trade_count=4211,
                )
            ),
            self.DATA_START,
            self.DATA_END,
        )
        self._app._connect_signals()

        recorded = self._recorded()
        self.assertEqual(
            "/recordings/live.sqlite", recorded["market_data_source"]
        )
        self.assertEqual("20260920T100000Z-abc123", recorded["source_run_id"])
        self.assertEqual(4211, recorded["market_data_trade_count"])
        self.assertEqual("RECORDED", recorded["market_data_mode"])

    def test_a_replay_gets_a_run_id_of_its_own(self):
        """Two replays of one recording are two runs, so neither inherits
        the id of the run that recorded the data."""
        source_run_id = "20260920T100000Z-abc123"
        second = EngineRuntime(
            symbol="BTC/USD",
            database_name=f"{self._folder.name}/second.sqlite",
            logfile_name=f"{self._folder.name}/second.log",
        )
        try:
            for app in (self._app, second):
                app.use_recorded_market_data(
                    self._data_source(
                        ReplayInput(
                            source="/recordings/live.sqlite",
                            source_run_id=source_run_id,
                        )
                    ),
                    self.DATA_START,
                    self.DATA_END,
                )

            first_id = self._app._engine_run.run_id
            second_id = second._engine_run.run_id
            self.assertNotEqual(first_id, second_id)
            self.assertNotIn(source_run_id, (first_id, second_id))
            self.assertEqual(
                source_run_id, self._app._engine_run.source_run_id
            )
            self.assertEqual(source_run_id, second._engine_run.source_run_id)
        finally:
            second._signal_recorder.close()

    def test_the_replays_own_timestamps_are_not_the_datas(self):
        self._app.use_recorded_market_data(
            self._data_source(ReplayInput(source="/recordings/live.sqlite")),
            self.DATA_START,
            self.DATA_END,
        )
        self._app._connect_signals()
        self._app.stop()

        recorded = self._recorded()
        self.assertEqual(
            self.DATA_START.timestamp(), recorded["market_data_started_at"]
        )
        self.assertEqual(
            self.DATA_END.timestamp(), recorded["market_data_ended_at"]
        )
        self.assertGreater(recorded["started_at"], self.DATA_END.timestamp())
        self.assertGreaterEqual(recorded["ended_at"], recorded["started_at"])

    def test_a_replay_ended_while_the_engine_clock_is_still_historical(self):
        """A replay moves the engine's clock through the interval it reads,
        and a feed that fails part way leaves it there. The run's own end
        is the machine's time regardless."""
        self._app.use_recorded_market_data(
            self._data_source(ReplayInput(source="/recordings/live.sqlite")),
            self.DATA_START,
            self.DATA_END,
        )
        self._app._connect_signals()
        time_manager().claim_admin(self)
        try:
            time_manager().use_fake_time(self.DATA_START, admin=self)
            self._app.stop()
        finally:
            time_manager().reset(admin=self)

        self.assertGreater(
            self._recorded()["ended_at"], self.DATA_END.timestamp()
        )

    def test_a_live_run_records_no_replay_source(self):
        self._app.use_market_data_service(
            _market_data_feed(MarketDataMode.REALTIME)
        )
        self._app._connect_signals()

        recorded = self._recorded()
        self.assertEqual("", recorded["market_data_source"])
        self.assertIsNone(recorded["source_run_id"])
        self.assertIsNone(recorded["market_data_started_at"])
        self.assertIsNone(recorded["market_data_trade_count"])


class TestRunConfigurationSnapshot(unittest.IsolatedAsyncioTestCase):
    """What a run records about its own configuration, and when."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._db = f"{self._folder.name}/config.sqlite"
        self._params_db = f"{self._folder.name}/params.sqlite"

    def tearDown(self):
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if isinstance(handler, SQLiteHandler):
                root_logger.removeHandler(handler)
                handler.close()
        self._folder.cleanup()

    def _make_app(self, parameter_service=None) -> EngineRuntime:
        return EngineRuntime(
            symbol="BTC/USD",
            exchange="Binance.US",
            database_name=self._db,
            logfile_name=f"{self._folder.name}/config.log",
            parameter_service=parameter_service,
        )

    async def _run(
        self,
        app: EngineRuntime,
        connect=None,
        market_data_mode: MarketDataMode = MarketDataMode.RECORDED,
    ) -> None:
        async def nothing(symbol, *args):
            if connect is not None:
                connect()

        app.use_market_data_service(
            SimpleNamespace(connect=nothing, market_data_mode=market_data_mode)
        )
        with patch.object(EngineRuntime, "THREAD_ENABLED", False):
            await app.run_start()
        app._signal_recorder.close()

    def _rows(self, table: str) -> list[dict]:
        with closing(sqlite3.connect(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()
            ]

    def _pushed(self, *changes: ParameterChange) -> LiveParameterService:
        store = ParameterStore(self._params_db)
        try:
            store.push(list(changes))
        finally:
            store.close()
        return LiveParameterService(self._params_db)

    async def test_a_run_records_the_parameters_it_started_with(self):
        app = self._make_app()
        await self._run(app)

        captured = {
            (row["group_name"], row["field_name"]): row["value"]
            for row in self._rows("run_parameter")
        }

        self.assertEqual(
            MarketMakingParameters().quote_size,
            captured[("MarketMakingParameters", "quote_size")],
        )
        self.assertTrue(
            all(
                row["run_id"] == app._engine_run.run_id
                for row in self._rows("run_parameter")
            )
        )

    async def test_an_override_pushed_before_the_run_is_in_the_snapshot(self):
        """The snapshot is what the first decision was made under, so it
        is taken after whatever was already in the store is loaded."""
        service = self._pushed(
            ParameterChange(
                "MarketMakingParameters", "quote_size", ALL_SYMBOLS, 0.004
            ),
            ParameterChange(
                "KrakenExecutionParameters",
                "poll_interval",
                ALL_SYMBOLS,
                2.5,
            ),
        )
        app = self._make_app(service)
        execution = _ConfigurableExecution()
        app.use_execution_service(execution)
        await self._run(app, market_data_mode=MarketDataMode.REALTIME)

        captured = {
            (row["group_name"], row["field_name"]): row["value"]
            for row in self._rows("run_parameter")
        }

        self.assertEqual(
            0.004, captured[("MarketMakingParameters", "quote_size")]
        )
        self.assertIs(service.values(), execution.parameters)
        self.assertEqual(
            2.5,
            execution.parameters.get(KrakenExecutionParameters).poll_interval,
        )

    async def test_the_snapshot_is_taken_before_the_first_tick(self):
        """The snapshot has to be what the first decision was made under,
        so it is published before the feed delivers anything."""
        order: list[str] = []
        event = signal("run_parameter")

        def note(sender, run_parameter):
            order.append("snapshot")

        event.connect(note)
        try:
            await self._run(
                self._make_app(), connect=lambda: order.append("tick")
            )
        finally:
            event.disconnect(note)

        self.assertEqual("snapshot", order[0])
        self.assertEqual("tick", order[-1])

    async def test_a_run_records_the_code_and_assumptions_it_ran_under(self):
        app = self._make_app()
        app.use_execution_service(
            MockExecutionService(BinanceUsFeeSchedule, health_monitor=None)
        )
        await self._run(app)

        environment = self._rows("run_environment")

        self.assertEqual(1, len(environment))
        recorded = environment[0]
        self.assertEqual(40, len(recorded["commit"]))
        self.assertIn(recorded["working_tree_clean"], (0, 1))
        self.assertEqual("MockExecutionService", recorded["execution_service"])
        self.assertEqual(
            "BinanceUsFeeSchedule",
            recorded["execution_simulation.fee_schedule"],
        )
        self.assertEqual(
            BinanceUsFeeSchedule().taker_rate,
            recorded["execution_simulation.taker_rate"],
        )
        self.assertEqual(
            "QueuePosition", recorded["execution_simulation.queue_model"]
        )
        self.assertIsNone(
            recorded["execution_simulation.order_latency_seconds"]
        )
        self.assertIsNone(recorded["execution_simulation.random_seed"])

    async def test_a_run_against_a_real_venue_records_no_assumptions(self):
        app = self._make_app()
        app.use_execution_service(_ConfigurableExecution())
        await self._run(app, market_data_mode=MarketDataMode.REALTIME)

        self.assertIsNone(
            self._rows("run_environment")[0]["execution_simulation"]
        )

    async def test_the_snapshot_holds_no_field_that_might_be_a_secret(self):
        app = self._make_app()
        await self._run(app)

        self.assertFalse(
            [
                row
                for row in self._rows("run_parameter")
                if looks_secret(row["field_name"])
            ]
        )

    async def test_a_second_run_in_one_recording_keeps_the_firsts_snapshot(
        self,
    ):
        """An earlier run's configuration is what it ran under and must
        not be rewritten by a later one, whatever the store holds by
        then."""
        first = self._make_app()
        await self._run(first)
        second = self._make_app(
            self._pushed(
                ParameterChange(
                    "MarketMakingParameters", "quote_size", ALL_SYMBOLS, 0.004
                )
            )
        )
        await self._run(second)

        by_run = {}
        for row in self._rows("run_parameter"):
            if (row["group_name"], row["field_name"]) == (
                "MarketMakingParameters",
                "quote_size",
            ):
                by_run[row["run_id"]] = row["value"]

        self.assertEqual(
            MarketMakingParameters().quote_size,
            by_run[first._engine_run.run_id],
        )
        self.assertEqual(0.004, by_run[second._engine_run.run_id])


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

    async def test_real_execution_refuses_recorded_market_data(self):
        app = self._make_app().use_execution_service(_ConfigurableExecution())
        self.addCleanup(app._signal_recorder.close)
        feed = SimpleNamespace(
            connect=AsyncMock(), market_data_mode=MarketDataMode.RECORDED
        )
        app.use_market_data_service(feed)

        with self.assertRaisesRegex(
            ValueError, "Real execution cannot consume recorded market data"
        ):
            await app.run_start()

        self.assertIsNone(app._exec_service.parameters)
        feed.connect.assert_not_awaited()

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

    async def test_delivers_one_complete_revision_before_market_data(self):
        service = StaticParameterService(
            KrakenExecutionParameters(poll_interval=2.5)
        )
        execution = _ConfigurableExecution()
        app = self._make_app(service).use_execution_service(execution)

        async def connect(symbol, *args):
            self.assertIs(service.values(), execution.parameters)
            self.assertEqual("BTC/USD", execution.symbol)
            self.assertEqual(
                2.5,
                execution.parameters.get(
                    KrakenExecutionParameters, execution.symbol
                ).poll_interval,
            )

        app.use_market_data_service(SimpleNamespace(connect=connect))
        with patch.object(EngineRuntime, "THREAD_ENABLED", False):
            await app.run_start()

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
