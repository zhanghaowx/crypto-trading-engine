import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jolteon.app.base import ApplicationBase
from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
    parameter_service,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
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

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.ticks_seen += 1


class TestApplicationBaseFairPriceModel(unittest.TestCase):
    def _make_app(self, fair_price_model):
        return ApplicationBase(
            symbol="BTC/USD",
            database_name=f"{tempfile.gettempdir()}/test_base.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/test_base.log",
            fair_price_model=fair_price_model,
        )

    def test_connect_all_wires_a_subscribing_fair_price_model(self):
        model = SubscribingFairPriceModel()
        app = self._make_app(model)

        app.connect_all()
        signal("ticker_feed").send(
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


class TestApplicationBaseRunStart(unittest.IsolatedAsyncioTestCase):
    def _make_app(self):
        return ApplicationBase(
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

        with patch.object(ApplicationBase, "THREAD_ENABLED", False):
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
            thread, _, _ = ApplicationBase._start_thread(
                "MD", failing_connect()
            )
            thread.join(timeout=5)

        self.assertIn("MD got exception: feed blew up", "".join(logs.output))


if __name__ == "__main__":
    unittest.main()


class TestApplicationBaseParameterService(unittest.IsolatedAsyncioTestCase):
    def _make_app(self, parameter_service=None):
        return ApplicationBase(
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
        with patch.object(ApplicationBase, "THREAD_ENABLED", False):
            await app.run_start()

        self.assertEqual(1, service.stopped)

    async def test_stops_polling_even_when_the_feed_fails(self):
        service = _RecordingParameterService()
        app = self._make_app(service)

        async def connect(symbol, *args):
            raise RuntimeError("feed blew up")

        app.use_market_data_service(SimpleNamespace(connect=connect))
        with patch.object(ApplicationBase, "THREAD_ENABLED", False):
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
