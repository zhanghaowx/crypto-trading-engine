import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from jolteon.app.data import (
    read_latest_per_group,
    read_latest_row,
    read_table,
    reset_table_cache,
)


class TestReadTable(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

        self.write(
            'CREATE TABLE "order" (client_order_id TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('1', 100.0)",
        )

        # Rows already read are held in the session, which outlives a test
        reset_table_cache()

    def tearDown(self):
        reset_table_cache()
        self._tmpdir.cleanup()

    def write(self, *statements: str, db_path: str | None = None) -> None:
        """
        Run each statement against the database and close the connection.

        Windows refuses to remove a file that is still open, so a
        connection left for the garbage collector to close fails the
        temporary directory's cleanup in tearDown.
        """
        with closing(sqlite3.connect(db_path or self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def insert(self, client_order_id: str, price: float) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                'INSERT INTO "order" VALUES (?, ?)', (client_order_id, price)
            )
            conn.commit()

    def test_reads_table_named_after_a_reserved_sql_keyword(self):
        # "order" is a reserved SQL keyword; an unquoted "SELECT * FROM
        # order" fails as a syntax error rather than returning rows.
        df = read_table(self.db_path, "order")

        self.assertEqual(1, len(df))
        self.assertEqual("1", df.iloc[0]["client_order_id"])

    def test_missing_table_returns_empty_dataframe(self):
        df = read_table(self.db_path, "does_not_exist")

        self.assertTrue(df.empty)

    def test_missing_database_file_returns_empty_dataframe(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        df = read_table(missing_path, "order")

        self.assertTrue(df.empty)

    def test_returns_rows_added_since_the_last_read(self):
        self.assertEqual(1, len(read_table(self.db_path, "order")))

        self.insert("2", 200.0)
        self.insert("3", 300.0)

        df = read_table(self.db_path, "order")
        self.assertEqual(["1", "2", "3"], list(df["client_order_id"]))
        self.assertEqual([100.0, 200.0, 300.0], list(df["price"]))

    def test_does_not_re_read_rows_it_already_has(self):
        """
        The whole point is that rows already fetched are not fetched again,
        which is visible as an edit to an old row not being picked up.
        """
        read_table(self.db_path, "order")

        self.write('UPDATE "order" SET price = 999.0')
        self.insert("2", 200.0)

        df = read_table(self.db_path, "order")
        # The stale row keeps its original price; only the new row is read
        self.assertEqual([100.0, 200.0], list(df["price"]))

    def test_reads_a_table_with_a_primary_key_in_full(self):
        """
        A row under a primary key is rewritten in place, and an update
        leaves the row id alone, so such a table cannot be read forward.
        """
        self.write(
            "CREATE TABLE candle (start_time REAL PRIMARY KEY, close REAL)",
            "INSERT INTO candle VALUES (1.0, 100.0)",
        )

        self.assertEqual(
            [100.0], list(read_table(self.db_path, "candle")["close"])
        )

        self.write("UPDATE candle SET close = 150.0 WHERE start_time = 1")

        # The update to the open candle is picked up, not missed
        self.assertEqual(
            [150.0], list(read_table(self.db_path, "candle")["close"])
        )

    def test_starts_over_when_the_recording_is_replaced(self):
        """
        Restarting the engine onto a fresh database restarts the row ids,
        so rows already held would otherwise mask the new recording.
        """
        self.insert("2", 200.0)
        self.assertEqual(2, len(read_table(self.db_path, "order")))

        self.write('DELETE FROM "order"')
        self.insert("fresh", 1.0)

        df = read_table(self.db_path, "order")
        self.assertEqual(["fresh"], list(df["client_order_id"]))

    def test_each_database_is_tracked_separately(self):
        other_path = str(Path(self._tmpdir.name) / "other.sqlite")
        self.write(
            'CREATE TABLE "order" (client_order_id TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('other', 1.0)",
            db_path=other_path,
        )

        self.assertEqual(
            ["1"], list(read_table(self.db_path, "order")["client_order_id"])
        )
        self.assertEqual(
            ["other"],
            list(read_table(other_path, "order")["client_order_id"]),
        )

    def test_caller_may_add_columns_without_affecting_the_next_read(self):
        df = read_table(self.db_path, "order")
        df["time"] = 0

        self.assertNotIn("time", read_table(self.db_path, "order").columns)

    @mock.patch("jolteon.app.data._MAX_CACHED_ROWS", 2)
    def test_caps_cached_rows_to_bound_session_memory(self):
        self.insert("2", 200.0)
        self.insert("3", 300.0)

        df = read_table(self.db_path, "order")

        self.assertEqual(["2", "3"], list(df["client_order_id"]))


class TestReadLatestRow(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def write(self, *statements: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def test_missing_database_file_returns_none(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        self.assertIsNone(read_latest_row(missing_path, "ticker_feed"))

    def test_missing_table_returns_none(self):
        self.write("CREATE TABLE other (a INTEGER)")

        self.assertIsNone(read_latest_row(self.db_path, "does_not_exist"))

    def test_returns_only_the_most_recently_inserted_row(self):
        self.write(
            "CREATE TABLE ticker_feed (price REAL)",
            "INSERT INTO ticker_feed VALUES (1.0)",
            "INSERT INTO ticker_feed VALUES (2.0)",
        )

        row = read_latest_row(self.db_path, "ticker_feed")

        self.assertEqual(2.0, row["price"])


class TestReadLatestPerGroup(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def write(self, *statements: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def test_missing_database_file_returns_empty_dataframe(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        df = read_latest_per_group(missing_path, "heartbeat", "sender")

        self.assertTrue(df.empty)

    def test_missing_table_returns_empty_dataframe(self):
        self.write("CREATE TABLE other (a INTEGER)")

        df = read_latest_per_group(self.db_path, "does_not_exist", "sender")

        self.assertTrue(df.empty)

    def test_returns_the_latest_row_for_each_distinct_group_value(self):
        self.write(
            'CREATE TABLE "order" (side TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('BUY', 1.0)",
            "INSERT INTO \"order\" VALUES ('BUY', 2.0)",
            "INSERT INTO \"order\" VALUES ('SELL', 3.0)",
        )

        df = read_latest_per_group(self.db_path, "order", "side")

        self.assertEqual(
            {"BUY": 2.0, "SELL": 3.0}, dict(zip(df["side"], df["price"]))
        )
