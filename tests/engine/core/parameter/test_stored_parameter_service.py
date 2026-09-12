import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.parameter_applied import (
    REJECTED,
    TAKEN,
    UNKNOWN,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterOverride,
    ParameterStore,
    override_of,
)
from jolteon.engine.core.parameter.poll_parameters import (
    ParameterPollParameters,
)
from jolteon.engine.core.parameter.stored_parameter_service import (
    StoredParameterService,
)


@dataclass(frozen=True)
class QuotingParameters(ParameterGroup):
    quote_size: float = parameter(0.0005, minimum=0.0, maximum=1.0)
    depth: int = parameter(10, minimum=1, maximum=100)


class StoredParameterServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "params.sqlite")
        self.store = ParameterStore(self.path)
        self.addCleanup(self.store.close)

        patcher = patch.object(
            parameter_catalog,
            "GROUPS",
            (QuotingParameters, ParameterPollParameters),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.applied = []

    def service(self) -> StoredParameterService:
        service = StoredParameterService(self.path)
        service.parameter_applied_event.connect(self._on_applied)
        self.addCleanup(service.stop)
        return service

    def _on_applied(self, _, parameter_applied):
        self.applied.append(parameter_applied)


class TestReadingStoredValues(StoredParameterServiceTestCase):
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
        self.store.push([override_of("QuotingParameters", "quote_size", 0.01)])
        service = self.service()
        service.start()
        self.assertEqual(0.01, service.get(QuotingParameters).quote_size)

    def test_keeps_an_int_field_an_int(self):
        self.store.push([override_of("QuotingParameters", "depth", 4)])
        service = self.service()
        service.start()
        self.assertIsInstance(service.get(QuotingParameters).depth, int)

    def test_prefers_a_symbols_own_value(self):
        self.store.push(
            [
                override_of("QuotingParameters", "quote_size", 0.01),
                ParameterOverride(
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

    def test_a_symbol_falls_back_to_the_default_for_other_groups(self):
        self.store.push(
            [
                ParameterOverride(
                    "QuotingParameters", "quote_size", "BTC/USD", 0.05
                )
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(
            1.0,
            service.get(
                ParameterPollParameters, "BTC/USD"
            ).interval_in_seconds,
        )


class TestPickingUpChanges(StoredParameterServiceTestCase):
    def test_a_push_reaches_the_engine_on_the_next_refresh(self):
        service = self.service()
        service.start()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service._refresh()

        self.assertEqual(0.02, service.get(QuotingParameters).quote_size)

    def test_refreshing_with_nothing_committed_rebuilds_nothing(self):
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
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
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
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

        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service._refresh()
        service._refresh()

        self.assertEqual(first + 1, service.values().revision)


class TestRefusingABadPush(StoredParameterServiceTestCase):
    def test_keeps_the_running_values_when_a_value_is_out_of_bounds(self):
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        self.store.push([override_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()

        self.assertEqual(0.02, service.get(QuotingParameters).quote_size)

    def test_reports_why_an_out_of_bounds_value_was_refused(self):
        service = self.service()
        service.start()
        self.applied.clear()

        self.store.push([override_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()

        refused = [a for a in self.applied if a.status == REJECTED]
        self.assertEqual(1, len(refused))
        self.assertEqual("quote_size", refused[0].field_name)
        self.assertIn("at most 1.0", refused[0].reason)

    def test_reports_a_parameter_this_engine_does_not_have(self):
        service = self.service()
        service.start()
        self.applied.clear()

        self.store.push([override_of("QuotingParameters", "invented", 1.0)])
        service._refresh()

        unknown = [a for a in self.applied if a.status == UNKNOWN]
        self.assertEqual(["invented"], [a.field_name for a in unknown])

    def test_an_unknown_field_does_not_block_a_good_one(self):
        self.store.push(
            [
                override_of("QuotingParameters", "invented", 1.0),
                override_of("QuotingParameters", "quote_size", 0.03),
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
        self.store.push([override_of("QuotingParameters", "depth", 20)])
        service = self.service()
        service.start()

        self.store.push([override_of("QuotingParameters", "depth", "ten")])
        service._refresh()

        self.assertEqual(20, service.get(QuotingParameters).depth)

    def test_reports_why_an_uncoercible_value_was_refused(self):
        service = self.service()
        service.start()
        self.applied.clear()

        self.store.push([override_of("QuotingParameters", "depth", "ten")])
        service._refresh()

        refused = [a for a in self.applied if a.status == REJECTED]
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
                override_of("QuotingParameters", "quote_size", 0.03),
                override_of("QuotingParameters", "depth", "ten"),
            ]
        )
        service._refresh()

        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)

    def test_raises_a_warning_while_a_push_stands_refused(self):
        service = self.service()
        service.start()
        self.store.push([override_of("QuotingParameters", "quote_size", 9.0)])
        service._refresh()
        self.assertGreater(len(service._issues), 1)

        self.store.push([override_of("QuotingParameters", "quote_size", 0.03)])
        service._refresh()
        self.assertEqual(1, len(service._issues))


class TestReportingWhatWasApplied(StoredParameterServiceTestCase):
    def test_says_nothing_about_a_field_nobody_pushed(self):
        service = self.service()
        service.start()
        self.assertEqual([], self.applied)

    def test_reports_a_pushed_field_as_taken(self):
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        self.assertEqual(1, len(self.applied))
        self.assertEqual(TAKEN, self.applied[0].status)
        self.assertEqual("0.02", self.applied[0].stored_value)

    def test_a_field_is_behind_until_a_component_reads_its_group(self):
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()

        first = self.applied[-1]
        self.assertLess(first.observed_revision, first.revision)

        service.get(QuotingParameters)
        service._refresh()

        latest = self.applied[-1]
        self.assertEqual(latest.revision, latest.observed_revision)

    def test_stops_repeating_itself_once_nothing_is_moving(self):
        self.store.push([override_of("QuotingParameters", "quote_size", 0.02)])
        service = self.service()
        service.start()
        service.get(QuotingParameters)
        service._refresh()

        self.applied.clear()
        service._refresh()
        service._refresh()
        self.assertEqual([], self.applied)


class TestPollingThread(StoredParameterServiceTestCase):
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
            [
                override_of(
                    "ParameterPollParameters", "interval_in_seconds", 0.1
                )
            ]
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
            [
                override_of(
                    "ParameterPollParameters", "interval_in_seconds", 2.5
                )
            ]
        )
        service = self.service()
        service.start()
        self.assertEqual(
            2.5, service.get(ParameterPollParameters).interval_in_seconds
        )
