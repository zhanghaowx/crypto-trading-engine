import contextlib
import io
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
    use_parameter_service,
)
from jolteon.engine.core.sqlite_writer import (
    SQLiteWriter,
    SqliteWriterParameters,
)


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

    def writer_with(self, **tunables) -> SQLiteWriter:
        """A writer reading the given tunables instead of the declared
        defaults. SQLiteWriter reads them from the global service at
        construction, so the service has to be in place first.

        It replaces this test's writer rather than joining it, since
        tearDown removes the database and runs before any cleanup
        registered here would have closed a second one."""
        use_parameter_service(
            StaticParameterService(SqliteWriterParameters(**tunables))
        )
        self.addCleanup(use_parameter_service, StaticParameterService())
        self.writer.close()
        self.writer = SQLiteWriter(self.database_filepath)
        return self.writer

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
                "jolteon.engine.core.sqlite_writer.sqlite3.connect",
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

    def test_empty_row_writes_nothing(self):
        self.writer.put("t", {})
        self.writer.flush()

        self.assertEqual(
            [], self.query("SELECT name FROM sqlite_master WHERE name='t'")
        )

    def test_row_that_is_only_a_primary_key_is_not_duplicated(self):
        self.writer.put("t", {"id": 1}, primary_key="id")
        self.writer.flush()
        self.writer.put("t", {"id": 1}, primary_key="id")
        self.writer.flush()

        self.assertEqual([(1,)], self.query("SELECT id FROM t"))

    def test_a_burst_larger_than_one_batch_loses_nothing(self):
        """
        A burst the disk can't keep up with is committed in pieces, so the
        writer never holds the write lock for one huge transaction.

        The cap is set far below the burst rather than left at its
        declared 5000, so the split is forced instead of depending on how
        much the writer happened to drain before the lock stopped it.
        """
        total = 100
        writer = self.writer_with(max_batch=2)
        with closing(
            sqlite3.connect(self.database_filepath, isolation_level=None)
        ) as blocker:
            blocker.execute("BEGIN EXCLUSIVE")
            try:
                for i in range(total):
                    writer.put("t", {"a": i})
            finally:
                blocker.execute("ROLLBACK")

        writer.flush()
        self.assertEqual([(total,)], self.query("SELECT COUNT(*) FROM t"))

    def test_flush_gives_up_when_the_writer_thread_is_gone(self):
        """
        Nothing will ever set the flush marker once the writer thread has
        died, so waiting on it outright would hang the caller forever.
        """

        class _DeadThread:
            def __init__(self):
                self.checks = 0

            def is_alive(self):
                self.checks += 1
                return self.checks == 1

        self.writer.close()
        self.writer._thread = _DeadThread()

        self.writer.flush()

    def test_close_while_the_database_cannot_be_opened(self):
        """
        A shutdown requested before the writer gives up on opening the
        database must still return, reporting why nothing was written.
        """
        release = threading.Event()
        raised: list[BaseException] = []

        def blocked_connect(_self):
            release.wait(timeout=5)
            raise sqlite3.OperationalError("cannot open database")

        def close_writer():
            try:
                writer.close()
            except BaseException as e:
                raised.append(e)

        with patch.object(SQLiteWriter, "_connect", blocked_connect):
            writer = SQLiteWriter(self.database_filepath)
            writer.put("t", {"a": 1})

            closing_thread = threading.Thread(target=close_writer)
            closing_thread.start()
            release.set()
            closing_thread.join(timeout=5)

        self.assertFalse(closing_thread.is_alive())
        self.assertEqual(1, len(raised))
        self.assertIsInstance(raised[0], sqlite3.OperationalError)

    def test_close_quietly_reports_failure_on_stderr(self):
        """
        atexit has nowhere to raise to, and logging would feed the failure
        back into a writer of its own.
        """
        stderr = io.StringIO()
        with (
            patch.object(
                self.writer, "close", side_effect=sqlite3.OperationalError
            ),
            contextlib.redirect_stderr(stderr),
        ):
            self.writer._close_quietly()

        self.assertIn(
            f"Failed to write to {self.database_filepath}", stderr.getvalue()
        )
