import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
    change_of,
)


class TestParameterStore(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "params.sqlite")
        self.store = ParameterStore(self.path)
        # Before the directory goes, since Windows refuses to remove a
        # file the store still holds a read-only connection to.
        self.addCleanup(self.store.close)

    def _legacy_polling_setting(self, value=2.5, updated_at=1.0):
        self.store.push([])
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT INTO parameter_override VALUES "
                "('ParameterPollParameters', 'interval_in_seconds', "
                "'', ?, ?)",
                (str(value), updated_at),
            )
            conn.commit()

    def test_reads_legacy_polling_settings_without_writing(self):
        self._legacy_polling_setting()
        self.assertEqual(
            [
                change_of(
                    "ParameterPollingSettings", "interval_in_seconds", 2.5
                )
            ],
            self.store.read(),
        )
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(
                "ParameterPollParameters",
                conn.execute(
                    "SELECT group_name FROM parameter_override"
                ).fetchone()[0],
            )

    def test_new_polling_change_replaces_legacy_value_and_keeps_history(self):
        self._legacy_polling_setting()
        self.store.push(
            [change_of("ParameterPollingSettings", "interval_in_seconds", 3.0)]
        )
        self.assertEqual(1, len(self.store.read()))
        self.assertEqual(3.0, self.store.read()[0].value)
        self.assertEqual(("2.5", "3.0"), self.store.changes()[0][3:5])

    def test_reset_by_new_group_name_removes_legacy_setting(self):
        self._legacy_polling_setting()
        self.store.reset("ParameterPollingSettings")
        self.assertEqual([], self.store.read())

    def test_duplicate_group_names_preserve_the_newest_value(self):
        for legacy_time, expected in ((1.0, 3.0), (3.0, 2.5)):
            with self.subTest(legacy_time=legacy_time):
                self.store.reset()
                self._legacy_polling_setting(updated_at=legacy_time)
                with closing(sqlite3.connect(self.path)) as conn:
                    conn.execute(
                        "INSERT INTO parameter_override VALUES "
                        "('ParameterPollingSettings', 'interval_in_seconds', "
                        "'', '3.0', 2.0)"
                    )
                    conn.commit()
                self.assertEqual(expected, self.store.read()[0].value)
                self.store.push([])
                self.assertEqual(1, len(self.store.read()))
                self.assertEqual(expected, self.store.read()[0].value)

    def test_a_store_nobody_has_pushed_to_reads_as_empty(self):
        self.assertFalse(Path(self.path).exists())
        self.assertEqual([], self.store.read())
        self.assertIsNone(self.store.data_version())
        self.assertEqual([], self.store.changes())

    def test_reads_back_what_was_pushed_with_its_own_type(self):
        self.store.push(
            [
                change_of("Quoting", "quote_size", 0.01),
                change_of("Quoting", "depth", 10),
                change_of("Quoting", "enabled", True),
            ]
        )
        by_field = {o.field_name: o.value for o in self.store.read()}
        self.assertEqual(0.01, by_field["quote_size"])
        self.assertIsInstance(by_field["depth"], int)
        self.assertIs(True, by_field["enabled"])

    def test_pushing_the_same_field_twice_leaves_one_saved_value(self):
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        self.store.push([change_of("Quoting", "quote_size", 0.02)])

        changes = self.store.read()
        self.assertEqual(1, len(changes))
        self.assertEqual(0.02, changes[0].value)

    def test_the_same_field_for_two_symbols_stays_two_changes(self):
        self.store.push(
            [
                ParameterChange("Quoting", "quote_size", "", 0.01),
                ParameterChange("Quoting", "quote_size", "BTC/USD", 0.02),
            ]
        )
        self.assertEqual(2, len(self.store.read()))

    def test_records_what_each_push_replaced(self):
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        self.store.push([change_of("Quoting", "quote_size", 0.02)])

        newest, older = self.store.changes()
        self.assertEqual("0.02", newest[4])
        self.assertEqual("0.01", newest[3])
        self.assertIsNone(older[3])

    def test_data_version_moves_only_when_something_was_committed(self):
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        first = self.store.data_version()
        self.assertIsNotNone(first)
        self.assertEqual(first, self.store.data_version())

        self.store.push([change_of("Quoting", "quote_size", 0.02)])
        self.assertNotEqual(first, self.store.data_version())

    def test_reset_drops_changes_and_records_dropping_them(self):
        self.store.push(
            [
                change_of("Quoting", "quote_size", 0.01),
                change_of("Skew", "scale", 2.0),
            ]
        )
        self.store.reset(group_name="Quoting")

        remaining = self.store.read()
        self.assertEqual(["Skew"], [o.group_name for o in remaining])
        self.assertIsNone(self.store.changes()[0][4])

    def test_reset_without_a_group_drops_everything(self):
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        self.store.reset()
        self.assertEqual([], self.store.read())

    def test_a_value_that_is_not_json_is_left_out(self):
        """
        Only the dashboard should be writing this file, but nothing stops
        something else from doing so. One unreadable row must not cost
        the engine the rows around it.
        """
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT INTO parameter_override VALUES "
                "('Quoting', 'depth', '', 'not json', 0.0)"
            )
            conn.commit()

        self.assertEqual(
            ["quote_size"], [o.field_name for o in self.store.read()]
        )

    def test_survives_a_file_that_is_not_a_database(self):
        Path(self.path).write_text("not a database")
        self.assertEqual([], self.store.read())
        self.assertEqual([], self.store.changes())

    def test_never_writes_through_the_engines_connection(self):
        self.store.push([change_of("Quoting", "quote_size", 0.01)])
        with closing(self.store._read_only()) as conn:
            with self.assertRaises(Exception):
                conn.execute("DELETE FROM parameter_override")
                conn.commit()
