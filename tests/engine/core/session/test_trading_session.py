import unittest
from datetime import datetime, timedelta, timezone

import pytz

from jolteon.engine.core.session.trading_session import (
    TradingSessionRun,
    trading_session_id,
    trading_session_id_at,
    trading_session_window,
)


class TestTradingSessionId(unittest.TestCase):
    def test_a_session_is_named_after_its_utc_day(self):
        self.assertEqual(
            "2026-09-20",
            trading_session_id(
                datetime(2026, 9, 20, 13, 45, tzinfo=timezone.utc)
            ),
        )

    def test_a_local_evening_belongs_to_the_next_utc_day(self):
        """New York's evening is already tomorrow in UTC, and the session
        is the UTC day rather than the reader's."""
        evening = pytz.timezone("America/New_York").localize(
            datetime(2026, 9, 20, 21, 0)
        )

        self.assertEqual("2026-09-21", trading_session_id(evening))

    def test_a_moment_without_a_timezone_is_read_as_utc(self):
        self.assertEqual(
            "2026-09-20", trading_session_id(datetime(2026, 9, 20, 23, 59))
        )

    def test_midnight_opens_the_next_session(self):
        midnight = datetime(2026, 9, 21, tzinfo=timezone.utc)

        self.assertEqual(
            "2026-09-20",
            trading_session_id(midnight - timedelta(microseconds=1)),
        )
        self.assertEqual("2026-09-21", trading_session_id(midnight))

    def test_a_session_is_named_from_epoch_seconds_too(self):
        moment = datetime(2026, 9, 20, 13, 45, tzinfo=timezone.utc)

        self.assertEqual(
            "2026-09-20", trading_session_id_at(moment.timestamp())
        )

    def test_sessions_sort_in_the_order_they_happened(self):
        days = [
            trading_session_id(datetime(2026, 9, day, tzinfo=timezone.utc))
            for day in (21, 19, 20)
        ]

        self.assertEqual(
            ["2026-09-19", "2026-09-20", "2026-09-21"], sorted(days)
        )


class TestTradingSessionWindow(unittest.TestCase):
    def test_a_session_runs_from_midnight_to_midnight(self):
        opens, closes = trading_session_window("2026-09-20")

        self.assertEqual(datetime(2026, 9, 20, tzinfo=timezone.utc), opens)
        self.assertEqual(datetime(2026, 9, 21, tzinfo=timezone.utc), closes)

    def test_the_end_belongs_to_the_next_session(self):
        _, closes = trading_session_window("2026-09-20")

        self.assertEqual("2026-09-21", trading_session_id(closes))


class TestTradingSessionRunIdentity(unittest.TestCase):
    def test_two_runs_of_one_session_are_recorded_apart(self):
        morning = TradingSessionRun.identity("2026-09-20", "run-a")
        afternoon = TradingSessionRun.identity("2026-09-20", "run-b")

        self.assertNotEqual(morning, afternoon)
