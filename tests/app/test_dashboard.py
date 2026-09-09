import sqlite3
import tempfile
import unittest
from pathlib import Path

from jolteon.app.dashboard import read_table


class TestReadTable(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

        conn = sqlite3.connect(self.db_path)
        conn.execute('CREATE TABLE "order" (client_order_id TEXT, price REAL)')
        conn.execute("INSERT INTO \"order\" VALUES ('1', 100.0)")
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmpdir.cleanup()

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
