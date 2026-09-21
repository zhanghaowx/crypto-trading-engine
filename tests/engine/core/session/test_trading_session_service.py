import unittest
from datetime import datetime, timedelta, timezone

from jolteon.engine.core.session.trading_session import TradingSessionRun
from jolteon.engine.core.session.trading_session_service import (
    TradingSessionService,
)


def _at(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


class TestTradingSessionService(unittest.TestCase):
    def setUp(self):
        self.recorded = list[TradingSessionRun]()
        self.service = TradingSessionService(
            run_id="run-a", exchange="Kraken", symbol="BTC/USD"
        )
        self.service.trading_session_run_event.connect(self._record)

    def tearDown(self):
        self.service.trading_session_run_event.disconnect(self._record)

    def _record(self, _, trading_session_run: TradingSessionRun):
        # Recorded as it stood when sent: the service rewrites the one row
        # it holds, and a list of references would all read as the last.
        self.recorded.append(TradingSessionRun(**vars(trading_session_run)))

    def test_the_first_moment_traded_opens_a_session(self):
        self.service.observe(_at(20, 9))

        self.assertEqual("2026-09-20", self.service.current_session_id)
        self.assertEqual(1, len(self.recorded))
        opened = self.recorded[0]
        self.assertEqual("2026-09-20", opened.session_id)
        self.assertEqual("run-a", opened.run_id)
        self.assertEqual("Kraken", opened.exchange)
        self.assertEqual("BTC/USD", opened.symbol)
        self.assertEqual(_at(20, 9), opened.first_seen_at)

    def test_trading_on_through_the_day_records_nothing_new(self):
        self.service.observe(_at(20, 9))
        self.service.observe(_at(20, 9) + timedelta(seconds=1))

        self.assertEqual(1, len(self.recorded))

    def test_crossing_midnight_closes_one_session_and_opens_the_next(self):
        self.service.observe(_at(20, 23, 59))
        self.recorded.clear()

        self.service.observe(_at(21, 0, 0))

        self.assertEqual("2026-09-21", self.service.current_session_id)
        closed, opened = self.recorded
        self.assertEqual("2026-09-20", closed.session_id)
        self.assertEqual(_at(21), closed.last_seen_at)
        self.assertEqual("2026-09-21", opened.session_id)
        self.assertEqual(_at(21), opened.first_seen_at)

    def test_one_run_may_span_several_sessions(self):
        for day in (20, 21, 22):
            self.service.observe(_at(day, 12))

        self.assertEqual(
            ["2026-09-20", "2026-09-21", "2026-09-22"],
            sorted({run.session_id for run in self.recorded}),
        )
        self.assertEqual({"run-a"}, {run.run_id for run in self.recorded})

    def test_a_session_still_being_traded_is_written_again_as_it_goes(self):
        self.service.observe(_at(20, 9))
        self.recorded.clear()

        self.service.observe(_at(20, 9) + timedelta(seconds=61))

        self.assertEqual(1, len(self.recorded))
        self.assertEqual(
            _at(20, 9) + timedelta(seconds=61), self.recorded[0].last_seen_at
        )
        self.assertEqual(_at(20, 9), self.recorded[0].first_seen_at)

    def test_stopping_records_where_the_engine_left_the_session(self):
        self.service.observe(_at(20, 9))
        self.recorded.clear()

        self.service.stop()

        self.assertEqual(1, len(self.recorded))
        self.assertIsNone(self.service.current_session_id)

    def test_stopping_twice_records_nothing_the_second_time(self):
        self.service.observe(_at(20, 9))
        self.service.stop()
        self.recorded.clear()

        self.service.stop()

        self.assertEqual([], self.recorded)

    def test_two_runs_of_one_session_are_recorded_apart(self):
        self.service.observe(_at(20, 9))
        other = TradingSessionService(
            run_id="run-b", exchange="Kraken", symbol="BTC/USD"
        )
        other.trading_session_run_event.connect(self._record)
        try:
            other.observe(_at(20, 15))
        finally:
            other.trading_session_run_event.disconnect(self._record)

        self.assertEqual(
            {"2026-09-20"}, {run.session_id for run in self.recorded}
        )
        self.assertEqual(2, len({run.session_run_id for run in self.recorded}))
