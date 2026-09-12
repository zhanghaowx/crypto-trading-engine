import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from jolteon.engine.core.parameter.parameter_store import (
    ParameterOverride,
    ParameterStore,
    override_of,
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

    def test_a_store_nobody_has_pushed_to_reads_as_empty(self):
        self.assertFalse(Path(self.path).exists())
        self.assertEqual([], self.store.read())
        self.assertIsNone(self.store.data_version())
        self.assertEqual([], self.store.changes())

    def test_reads_back_what_was_pushed_with_its_own_type(self):
        self.store.push(
            [
                override_of("Quoting", "quote_size", 0.01),
                override_of("Quoting", "depth", 10),
                override_of("Quoting", "enabled", True),
            ]
        )
        by_field = {o.field_name: o.value for o in self.store.read()}
        self.assertEqual(0.01, by_field["quote_size"])
        self.assertIsInstance(by_field["depth"], int)
        self.assertIs(True, by_field["enabled"])

    def test_pushing_the_same_field_twice_leaves_one_override(self):
        self.store.push([override_of("Quoting", "quote_size", 0.01)])
        self.store.push([override_of("Quoting", "quote_size", 0.02)])

        overrides = self.store.read()
        self.assertEqual(1, len(overrides))
        self.assertEqual(0.02, overrides[0].value)

    def test_the_same_field_for_two_symbols_stays_two_overrides(self):
        self.store.push(
            [
                ParameterOverride("Quoting", "quote_size", "", 0.01),
                ParameterOverride("Quoting", "quote_size", "BTC/USD", 0.02),
            ]
        )
        self.assertEqual(2, len(self.store.read()))

    def test_records_what_each_push_replaced(self):
        self.store.push([override_of("Quoting", "quote_size", 0.01)])
        self.store.push([override_of("Quoting", "quote_size", 0.02)])

        newest, older = self.store.changes()
        self.assertEqual("0.02", newest[4])
        self.assertEqual("0.01", newest[3])
        self.assertIsNone(older[3])

    def test_data_version_moves_only_when_something_was_committed(self):
        self.store.push([override_of("Quoting", "quote_size", 0.01)])
        first = self.store.data_version()
        self.assertIsNotNone(first)
        self.assertEqual(first, self.store.data_version())

        self.store.push([override_of("Quoting", "quote_size", 0.02)])
        self.assertNotEqual(first, self.store.data_version())

    def test_reset_drops_overrides_and_records_dropping_them(self):
        self.store.push(
            [
                override_of("Quoting", "quote_size", 0.01),
                override_of("Skew", "scale", 2.0),
            ]
        )
        self.store.reset(group_name="Quoting")

        remaining = self.store.read()
        self.assertEqual(["Skew"], [o.group_name for o in remaining])
        self.assertIsNone(self.store.changes()[0][4])

    def test_reset_without_a_group_drops_everything(self):
        self.store.push([override_of("Quoting", "quote_size", 0.01)])
        self.store.reset()
        self.assertEqual([], self.store.read())

    def test_survives_a_file_that_is_not_a_database(self):
        Path(self.path).write_text("not a database")
        self.assertEqual([], self.store.read())
        self.assertEqual([], self.store.changes())

    def test_never_writes_through_the_engines_connection(self):
        self.store.push([override_of("Quoting", "quote_size", 0.01)])
        with closing(self.store._read_only()) as conn:
            with self.assertRaises(Exception):
                conn.execute("DELETE FROM parameter_override")
                conn.commit()
