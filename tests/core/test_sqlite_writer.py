import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from jolteon.core.sqlite_writer import SQLiteWriter


class TestSQLiteWriter(unittest.TestCase):
    def setUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )
        self.writer = SQLiteWriter(self.database_filepath)

    def tearDown(self):
        try:
            self.writer.close()
        except Exception:
            pass
        for suffix in ("", "-wal", "-shm"):
            path = self.database_filepath + suffix
            if os.path.exists(path):
                os.remove(path)

    def query(self, sql: str, db_path: str | None = None) -> list[tuple]:
        with closing(
            sqlite3.connect(db_path or self.database_filepath)
        ) as conn:
            return conn.execute(sql).fetchall()

    def columns(self, table: str) -> list[str]:
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [row[1] for row in info]

    def create_table(self, ddl: str) -> None:
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(ddl)
            conn.commit()

    def test_writes_rows(self):
        self.writer.put("t", {"a": 1, "b": "x"})
        self.writer.put("t", {"a": 2, "b": "y"})
        self.writer.flush()

        self.assertEqual(
            [(1, "x"), (2, "y")], self.query("SELECT a, b FROM t ORDER BY a")
        )

    def test_enables_wal(self):
        """
        The dashboard reads the same file while the engine writes it, which
        only works without blocking when the database is in WAL mode.
        """
        self.writer.put("t", {"a": 1})
        self.writer.flush()

        self.assertEqual([("wal",)], self.query("PRAGMA journal_mode"))

    def test_connect_falls_back_when_the_wal_switch_fails(self):
        """
        Another connection already holding the database can make the
        journal_mode=WAL switch itself raise OperationalError. The writer
        must keep the connection and carry on under whatever mode is
        already in effect, not fail to start.
        """

        class _RaiseOnWalSwitch(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql == "PRAGMA journal_mode=WAL":
                    raise sqlite3.OperationalError("database is locked")
                return super().execute(sql, *args, **kwargs)

        real_connect = sqlite3.connect

        def connect_with_flaky_wal(database, *args, **kwargs):
            return real_connect(
                database, *args, factory=_RaiseOnWalSwitch, **kwargs
            )

        fresh_path = f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        try:
            with patch(
                "jolteon.core.sqlite_writer.sqlite3.connect",
                side_effect=connect_with_flaky_wal,
            ):
                writer = SQLiteWriter(fresh_path)
                writer.put("t", {"a": 1})
                writer.flush()
            self.assertEqual([(1,)], self.query("SELECT a FROM t", fresh_path))
            writer.close()
        finally:
            for suffix in ("", "-wal", "-shm", "-journal"):
                path = fresh_path + suffix
                if os.path.exists(path):
                    os.remove(path)

    def test_adds_column_for_new_field(self):
        """
        A payload that grows a field must widen the table in place, never
        rewrite the rows already recorded.
        """
        self.writer.put("t", {"a": 1})
        self.writer.flush()
        self.writer.put("t", {"a": 2, "b": "new"})
        self.writer.flush()

        self.assertEqual(["a", "b"], self.columns("t"))
        self.assertEqual(
            [(1, None), (2, "new")],
            self.query("SELECT a, b FROM t ORDER BY a"),
        )

    def test_primary_key_updates_instead_of_duplicating(self):
        self.writer.put("t", {"k": 1, "v": "first"}, primary_key="k")
        self.writer.flush()
        self.writer.put("t", {"k": 1, "v": "second"}, primary_key="k")
        self.writer.flush()

        self.assertEqual([(1, "second")], self.query("SELECT k, v FROM t"))

    def test_primary_key_coalesces_within_one_batch(self):
        """
        Repeated updates of one key queued together collapse to a single
        row, so a payload re-sent many times under the same key costs one
        write.
        """
        for i in range(100):
            self.writer.put("t", {"k": 1, "v": i}, primary_key="k")
        self.writer.flush()

        self.assertEqual([(1, 99)], self.query("SELECT k, v FROM t"))

    def test_keeps_existing_schema_without_primary_key(self):
        """
        Databases recorded before primary keys were declared keep their own
        schema, so rows must still append rather than fail to upsert.
        """
        self.create_table("CREATE TABLE t (k, v)")

        self.writer.put("t", {"k": 1, "v": "first"}, primary_key="k")
        self.writer.put("t", {"k": 1, "v": "second"}, primary_key="k")
        self.writer.flush()

        self.assertEqual(2, len(self.query("SELECT * FROM t")))

    def test_flush_reports_write_failure(self):
        """
        Writes happen off the caller's thread, so a failure has to surface
        at the next flush instead of vanishing.
        """
        self.create_table("CREATE TABLE t (a NOT NULL)")

        self.writer.put("t", {"a": None})
        with self.assertRaises(sqlite3.IntegrityError):
            self.writer.flush()

        # The error is reported once, and the writer keeps working
        self.writer.put("t", {"a": 1})
        self.writer.flush()
        self.assertEqual([(1,)], self.query("SELECT a FROM t"))

    def test_flush_reports_failure_to_open_database(self):
        writer = SQLiteWriter(tempfile.gettempdir())
        writer.put("t", {"a": 1})
        with self.assertRaises(sqlite3.OperationalError):
            writer.flush()
        writer.close()

    def test_close_is_idempotent(self):
        self.writer.put("t", {"a": 1})
        self.writer.close()
        self.writer.close()

        self.assertEqual([(1,)], self.query("SELECT a FROM t"))

    def test_put_does_not_block_while_the_database_is_locked(self):
        """
        Producers are the market data thread and the engine's event loop, so
        a database that is busy must slow the writer thread down and never
        the callers of `put`.
        """
        with closing(
            sqlite3.connect(self.database_filepath, isolation_level=None)
        ) as blocker:
            # BEGIN EXCLUSIVE blocks the writer's commit under either
            # journal mode, so there's no need to set one here - doing so
            # would race the writer thread's own identical PRAGMA in setUp().
            blocker.execute("BEGIN EXCLUSIVE")
            try:
                started = time.monotonic()
                for i in range(1000):
                    self.writer.put("t", {"a": i})
                elapsed = time.monotonic() - started
            finally:
                blocker.execute("ROLLBACK")

        self.assertLess(elapsed, 1.0)

        # Once the lock is released the queued rows land, none of them lost
        self.writer.flush()
        self.assertEqual([(1000,)], self.query("SELECT COUNT(*) FROM t"))

    def test_prune_keeps_only_the_newest_rows(self):
        for i in range(10):
            self.writer.put("t", {"a": i})
        self.writer.flush()

        self.writer.prune("t", keep_last=3)
        self.writer.flush()

        self.assertEqual(
            [(7,), (8,), (9,)], self.query("SELECT a FROM t ORDER BY a")
        )

    def test_prune_of_a_table_never_written_to_is_a_no_op(self):
        """
        A prune request naming a table this writer has no schema for (never
        written to, or written to by an earlier process) must not raise
        "no such table" - there is nothing for it to trim.
        """
        self.writer.prune("never_written", keep_last=3)
        self.writer.flush()

    def test_concurrent_producers_lose_nothing(self):
        num_threads = 50
        rows_each = 20

        def worker(thread_id: int):
            for i in range(rows_each):
                self.writer.put("t", {"thread": thread_id, "i": i})

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            list(executor.map(worker, range(num_threads)))
        self.writer.flush()

        self.assertEqual(
            [(num_threads * rows_each,)],
            self.query("SELECT COUNT(*) FROM t"),
        )
