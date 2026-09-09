import sqlite3
import tempfile
import unittest
from pathlib import Path

from jolteon.app.data import read_table, reset_table_cache


class TestReadTable(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

        conn = sqlite3.connect(self.db_path)
        conn.execute('CREATE TABLE "order" (client_order_id TEXT, price REAL)')
        conn.execute("INSERT INTO \"order\" VALUES ('1', 100.0)")
        conn.commit()
        conn.close()

        # Rows already read are held in the session, which outlives a test
        reset_table_cache()

    def tearDown(self):
        reset_table_cache()
        self._tmpdir.cleanup()

    def insert(self, client_order_id: str, price: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT INTO "order" VALUES (?, ?)', (client_order_id, price)
            )

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

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE "order" SET price = 999.0')
        self.insert("2", 200.0)

        df = read_table(self.db_path, "order")
        # The stale row keeps its original price; only the new row is read
        self.assertEqual([100.0, 200.0], list(df["price"]))

    def test_reads_a_table_with_a_primary_key_in_full(self):
        """
        A row under a primary key is rewritten in place, and an update
        leaves the row id alone, so such a table cannot be read forward.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE candle (start_time REAL PRIMARY KEY, close REAL)"
            )
            conn.execute("INSERT INTO candle VALUES (1.0, 100.0)")

        self.assertEqual(
            [100.0], list(read_table(self.db_path, "candle")["close"])
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE candle SET close = 150.0 WHERE start_time = 1"
            )

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

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM "order"')
        self.insert("fresh", 1.0)

        df = read_table(self.db_path, "order")
        self.assertEqual(["fresh"], list(df["client_order_id"]))

    def test_each_database_is_tracked_separately(self):
        other_path = str(Path(self._tmpdir.name) / "other.sqlite")
        with sqlite3.connect(other_path) as conn:
            conn.execute(
                'CREATE TABLE "order" (client_order_id TEXT, price REAL)'
            )
            conn.execute("INSERT INTO \"order\" VALUES ('other', 1.0)")

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
