import unittest
from datetime import datetime, timezone

from jolteon.engine.core.session.engine_run import EngineRun, engine_run_id


class TestEngineRunId(unittest.TestCase):
    def test_a_run_is_named_after_when_it_started(self):
        started_at = datetime(2026, 9, 20, 14, 16, 5, tzinfo=timezone.utc)

        self.assertTrue(
            engine_run_id(started_at).startswith("20260920T141605Z-")
        )

    def test_two_runs_starting_in_the_same_second_are_told_apart(self):
        started_at = datetime(2026, 9, 20, 14, 16, 5, tzinfo=timezone.utc)

        self.assertNotEqual(
            engine_run_id(started_at), engine_run_id(started_at)
        )

    def test_runs_sort_in_the_order_they_started(self):
        first = engine_run_id(datetime(2026, 9, 20, 9, tzinfo=timezone.utc))
        second = engine_run_id(datetime(2026, 9, 20, 14, tzinfo=timezone.utc))

        self.assertEqual([first, second], sorted([second, first]))


class TestEngineRun(unittest.TestCase):
    def test_a_run_still_trading_has_no_end(self):
        run = EngineRun(
            run_id="run-a",
            exchange="Kraken",
            symbol="BTC/USD",
            started_at=datetime(2026, 9, 20, 9, tzinfo=timezone.utc),
        )

        self.assertIsNone(run.ended_at)
