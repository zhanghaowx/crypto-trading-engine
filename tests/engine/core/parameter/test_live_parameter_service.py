import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from jolteon.engine.core.event.signal_recorder import SignalRecorder
from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.live_parameter_service import (
    LiveParameterService,
)
from jolteon.engine.core.parameter.parameter_change_result import (
    REJECTED,
    TAKEN,
    UNKNOWN,
)
from jolteon.engine.core.parameter.parameter_polling_settings import (
    ParameterPollingSettings,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
    change_of,
)


@dataclass(frozen=True)
class QuotingParameters(ParameterGroup):
    quote_size: float = parameter(0.0005, minimum=0.0, maximum=1.0)
    depth: int = parameter(10, minimum=1, maximum=100)


class LiveParameterServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "params.sqlite")
        self.store = ParameterStore(self.path)
        self.addCleanup(self.store.close)

        patcher = patch.object(
            parameter_catalog,
            "GROUPS",
            (QuotingParameters, ParameterPollingSettings),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.results = []
        self.revisions = []

    def service(self) -> LiveParameterService:
        service = LiveParameterService(self.path)
        service.parameter_change_result_event.connect(self._on_result)
        service.parameter_group_revision_event.connect(self._on_revision)
        self.addCleanup(service.stop)
        return service

    def _on_result(self, _, parameter_change_result):
        self.results.append(parameter_change_result)

    def _on_revision(self, _, parameter_group_revision):
        self.revisions.append(parameter_group_revision)

    def quoting_revision(self):
        return next(
            r
            for r in reversed(self.revisions)
            if r.group_name == "QuotingParameters"
        )


class TestReadingStoredValues(LiveParameterServiceTestCase):
    def test_runs_on_declared_defaults_when_nothing_was_pushed(self):
        service = self.service()
        service.start()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

    def test_a_missing_store_is_a_normal_startup_not_a_failure(self):
        self.assertFalse(Path(self.path).exists())
        service = self.service()
        service.start()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

    def test_a_store_that_is_not_a_database_leaves_it_on_defaults(self):
        Path(self.path).write_text("not a database")
        service = self.service()
        service.start()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

    def test_takes_a_pushed_value_over_the_default(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.01)])
        service = self.service()
        service.start()
        self.assertEqual(0.01, service.get(QuotingParameters).quote_size)

    def test_keeps_an_int_field_an_int(self):
        self.store.push([change_of("QuotingParameters", "depth", 4)])
        service = self.service()
        service.start()
        self.assertIsInstance(service.get(QuotingParameters).depth, int)

    def test_prefers_a_symbols_own_value(self):
        self.store.push(
            [
                change_of("QuotingParameters", "quote_size", 0.01),
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 0.05
                ),
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(
            0.05, service.get(QuotingParameters, "BTC/USD").quote_size
        )
        self.assertEqual(0.01, service.get(QuotingParameters).quote_size)

    def test_a_symbols_own_value_sits_on_top_of_the_shared_ones(self):
        """
        Setting one field for one symbol must not quietly return the rest
        of that group to its declared defaults, which is what the symbol
        map used to do: it was built from the symbol's fields alone.
        """
        self.store.push(
            [
                change_of("QuotingParameters", "depth", 25),
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 0.05
                ),
            ]
        )
        service = self.service()
        service.start()

        btc = service.get(QuotingParameters, "BTC/USD")
        self.assertEqual(0.05, btc.quote_size)
        self.assertEqual(25, btc.depth)

    def test_a_symbol_keeps_the_declared_default_nobody_overrode(self):
        self.store.push(
            [
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 0.05
                )
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(10, service.get(QuotingParameters, "BTC/USD").depth)

    def test_a_symbol_falls_back_to_the_default_for_other_groups(self):
        self.store.push(
            [
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 0.05
                )
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(
            1.0,
            service.get(
                ParameterPollingSettings, "BTC/USD"
            ).interval_in_seconds,
        )


class TestPickingUpChanges(LiveParameterServiceTestCase):
    def test_a_push_reaches_the_engine_on_the_next_refresh(self):
        service = self.service()
        service.start()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service._refresh()

        self.assertEqual(0.02, service.get(QuotingParameters).quote_size)

    def test_refreshing_with_nothing_committed_rebuilds_nothing(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        before = service.values()
        service._refresh()
        self.assertIs(before, service.values())

    def test_polling_a_store_that_does_not_exist_changes_nothing(self):
        service = self.service()
        service.start()
        revision = service.values().revision

        for _ in range(5):
            service._refresh()

        self.assertEqual(revision, service.values().revision)

    def test_polling_an_unchanged_store_changes_nothing(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()
        revision = service.values().revision

        for _ in range(5):
            service._refresh()

        self.assertEqual(revision, service.values().revision)

    def test_reads_no_file_once_the_values_are_built(self):
        service = self.service()
        service.start()
        values = service.values()

        with patch("sqlite3.connect", side_effect=AssertionError("no I/O")):
            for _ in range(100):
                values.get(QuotingParameters)

        self.assertEqual(0.0005, values.get(QuotingParameters).quote_size)

    def test_each_push_advances_the_revision_once(self):
        service = self.service()
        service.start()
        first = service.values().revision

        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service._refresh()
        service._refresh()

        self.assertEqual(first + 1, service.values().revision)


class TestRefusingABadPush(LiveParameterServiceTestCase):
    def test_keeps_the_running_values_when_a_value_is_out_of_bounds(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        self.store.push([change_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()

        self.assertEqual(0.02, service.get(QuotingParameters).quote_size)

    def test_reports_why_an_out_of_bounds_value_was_refused(self):
        service = self.service()
        service.start()
        self.results.clear()

        self.store.push([change_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()

        refused = [a for a in self.results if a.status == REJECTED]
        self.assertEqual(1, len(refused))
        self.assertEqual("quote_size", refused[0].field_name)
        self.assertIn("at most 1.0", refused[0].reason)

    def test_keeps_the_running_values_when_a_symbols_value_is_out_of_bounds(
        self,
    ):
        service = self.service()
        service.start()

        self.store.push(
            [
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 9.0
                )
            ]
        )
        service._refresh()

        self.assertEqual(
            0.0005, service.get(QuotingParameters, "BTC/USD").quote_size
        )

    def test_reports_a_refused_symbol_value_against_that_symbol(self):
        service = self.service()
        service.start()
        self.results.clear()

        self.store.push(
            [
                ParameterChange(
                    "QuotingParameters", "quote_size", "BTC/USD", 9.0
                )
            ]
        )
        service._refresh()

        refused = [a for a in self.results if a.status == REJECTED]
        self.assertEqual(1, len(refused))
        self.assertEqual("BTC/USD", refused[0].symbol)
        self.assertIn("at most 1.0", refused[0].reason)

    def test_reports_a_parameter_this_engine_does_not_have(self):
        service = self.service()
        service.start()
        self.results.clear()

        self.store.push([change_of("QuotingParameters", "invented", 1.0)])
        service._refresh()

        unknown = [a for a in self.results if a.status == UNKNOWN]
        self.assertEqual(["invented"], [a.field_name for a in unknown])

    def test_an_unknown_field_does_not_block_a_good_one(self):
        self.store.push(
            [
                change_of("QuotingParameters", "invented", 1.0),
                change_of("QuotingParameters", "quote_size", 0.03),
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(0.03, service.get(QuotingParameters).quote_size)

    def test_keeps_running_when_a_value_cannot_become_its_type(self):
        """
        Bounds cannot catch this one: the value never gets far enough to
        be compared against them, since coercing it raises first.
        """
        self.store.push([change_of("QuotingParameters", "depth", 20)])
        service = self.service()
        service.start()

        self.store.push([change_of("QuotingParameters", "depth", "ten")])
        service._refresh()

        self.assertEqual(20, service.get(QuotingParameters).depth)

    def test_reports_why_an_uncoercible_value_was_refused(self):
        service = self.service()
        service.start()
        self.results.clear()

        self.store.push([change_of("QuotingParameters", "depth", "ten")])
        service._refresh()

        refused = [a for a in self.results if a.status == REJECTED]
        self.assertEqual(["depth"], [a.field_name for a in refused])
        self.assertIn("ten", refused[0].reason)

    def test_one_uncoercible_value_refuses_the_whole_push(self):
        """
        A push is one transaction to the engine as well as to the file,
        so it cannot half-apply: the good field would otherwise land on
        top of values the refused one was meant to go with.
        """
        service = self.service()
        service.start()

        self.store.push(
            [
                change_of("QuotingParameters", "quote_size", 0.03),
                change_of("QuotingParameters", "depth", "ten"),
            ]
        )
        service._refresh()

        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

    def test_raises_a_warning_while_a_push_stands_refused(self):
        service = self.service()
        service.start()
        self.store.push([change_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()
        self.assertGreater(len(service._issues), 1)

        self.store.push([change_of("QuotingParameters", "quote_size", 0.03)])
        service._refresh()
        self.assertEqual(1, len(service._issues))


class TestReportingChanges(LiveParameterServiceTestCase):
    def test_multiple_fields_share_one_group_revision(self):
        self.store.push(
            [
                change_of("QuotingParameters", "quote_size", 0.02),
                ParameterChange("QuotingParameters", "depth", "BTC/USD", 5),
            ]
        )
        service = self.service()
        service._refresh()

        self.assertEqual(2, len(self.results))
        self.assertEqual(
            1, sum(r.group_name == "QuotingParameters" for r in self.revisions)
        )
        self.results.clear()
        self.revisions.clear()
        service.get(QuotingParameters, "BTC/USD")
        service._refresh()
        self.assertEqual([], self.results)
        self.assertEqual(1, len(self.revisions))
        self.assertEqual(1, self.revisions[0].last_read_revision)

    def test_default_group_reads_are_reported_without_field_changes(self):
        service = self.service()
        service._refresh()
        self.assertIsNone(self.quoting_revision().last_read_revision)
        service.get(QuotingParameters)
        service._refresh()
        self.assertEqual(0, self.quoting_revision().last_read_revision)
        self.assertEqual([], self.results)

    def test_different_rejected_values_each_emit_a_result(self):
        service = self.service()
        for value in (9.0, 10.0):
            self.store.push(
                [change_of("QuotingParameters", "quote_size", value)]
            )
            service._refresh()
        self.assertEqual(
            ["9.0", "10.0"], [r.stored_value for r in self.results]
        )
        self.assertTrue(all(r.status == REJECTED for r in self.results))
        self.assertEqual(0, self.quoting_revision().current_revision)

    def test_recorder_persists_results_and_revisions_separately(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        recording = str(Path(self.directory.name) / "engine.sqlite")
        recorder = SignalRecorder(recording)
        self.addCleanup(recorder.close)
        recorder.start_recording()
        service._refresh()
        recorder.flush()
        with closing(sqlite3.connect(recording)) as conn:
            self.assertEqual(
                (1, None),
                conn.execute(
                    "SELECT current_revision, last_read_revision "
                    "FROM parameter_group_revision "
                    "WHERE group_name = 'QuotingParameters'"
                ).fetchone(),
            )
            service.get(QuotingParameters)
            service._refresh()
            recorder.flush()
            self.assertEqual(
                (1, 1),
                conn.execute(
                    "SELECT current_revision, last_read_revision "
                    "FROM parameter_group_revision "
                    "WHERE group_name = 'QuotingParameters'"
                ).fetchone(),
            )
            self.assertEqual(
                [(TAKEN, "0.02")],
                conn.execute(
                    "SELECT status, stored_value FROM parameter_change_result"
                ).fetchall(),
            )

    def test_says_nothing_about_a_field_nobody_pushed(self):
        service = self.service()
        service.start()
        self.assertEqual([], self.results)

    def test_reports_a_pushed_field_as_taken(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        self.assertEqual(1, len(self.results))
        self.assertEqual(TAKEN, self.results[0].status)
        self.assertEqual("0.02", self.results[0].stored_value)

    def test_a_field_is_behind_until_a_component_reads_its_group(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        first = self.quoting_revision()
        self.assertIsNone(first.last_read_revision)
        self.results.clear()

        service.get(QuotingParameters)
        service._refresh()

        latest = self.quoting_revision()
        self.assertEqual(latest.current_revision, latest.last_read_revision)
        self.assertEqual([], self.results)

    def test_stops_repeating_itself_once_nothing_is_moving(self):
        self.store.push([change_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()
        service.get(QuotingParameters)
        service._refresh()

        self.results.clear()
        service._refresh()
        service._refresh()
        self.assertEqual([], self.results)


class TestPollingThread(LiveParameterServiceTestCase):
    def test_starting_twice_leaves_one_thread(self):
        service = self.service()
        service.start()
        thread = service._thread
        service.start()
        self.assertIs(thread, service._thread)

    def test_stop_joins_the_thread(self):
        service = self.service()
        service.start()
        thread = service._thread
        service.stop()
        self.assertFalse(thread.is_alive())
        self.assertIsNone(service._thread)

    def test_a_refresh_that_raises_does_not_kill_the_poller(self):
        """
        The thread is the only thing carrying pushed values into the
        engine, so it has to survive whatever one refresh does. A dead
        poller looks exactly like a dashboard nobody is pushing from.
        """
        self.store.push(
            [change_of("ParameterPollingSettings", "interval_in_seconds", 0.1)]
        )
        service = self.service()
        service.start()

        refreshed = threading.Event()
        failures = []

        def failing_refresh():
            failures.append(None)
            refreshed.set()
            raise RuntimeError("boom")

        with patch.object(service, "_refresh", side_effect=failing_refresh):
            self.assertTrue(refreshed.wait(timeout=5))
            self.assertTrue(service._thread.is_alive())

        self.assertTrue(service._thread.is_alive())

    def test_stop_hands_back_the_store_file(self):
        """
        The store keeps one read-only connection open for as long as it
        is polled. Windows refuses to remove a file another handle still
        holds, so a session that stopped but never let go took out the
        temporary directory of whichever test ran next.
        """
        service = self.service()
        service.start()
        service.stop()
        self.assertIsNone(service._store._reader)

    def test_the_poll_interval_is_itself_a_parameter(self):
        self.store.push(
            [change_of("ParameterPollingSettings", "interval_in_seconds", 2.5)]
        )
        service = self.service()
        service.start()
        self.assertEqual(
            2.5, service.get(ParameterPollingSettings).interval_in_seconds
        )
