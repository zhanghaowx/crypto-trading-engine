import asyncio
import logging
import os
import sqlite3
import tempfile
import threading
import unittest
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pandas as pd
from freezegun import freeze_time

from jolteon.core.logging.logger import setup_global_logger


class TestLogging(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )

        # unittest.IsolatedAsyncioTestCase always runs with asyncio debug
        # mode on, which makes asyncio log a WARNING (propagated to the
        # root logger, and thus captured by the DB logger under test)
        # whenever a callback takes longer than its slow-callback
        # threshold. That happens often enough on loaded CI runners to
        # add unrelated rows to the logs table, so silence it here.
        self._asyncio_logger_level = logging.getLogger("asyncio").level
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    def tearDown(self):
        logging.getLogger("asyncio").setLevel(self._asyncio_logger_level)

        if os.path.exists(self.database_filepath):
            os.remove(self.database_filepath)

    def assert_number_of_logging(
        self,
        n_of_logging: int,
        conn: sqlite3.Connection,
        should_flush_logger: bool = False,
    ):
        if should_flush_logger:
            for log_handler in logging.getLogger().handlers:
                log_handler.flush()

        df = pd.read_sql_query(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='logs';",
            con=conn,
        )
        if len(df) == 0:
            self.assertEqual(n_of_logging, 0)
        else:
            df = pd.read_sql_query("SELECT * FROM logs", con=conn)
            self.assertEqual(n_of_logging, len(df))

    @freeze_time("2022-01-01 00:00:00 UTC")
    async def test_perform_logging_format(self):
        # Perform the logging and capture the log output
        with self.assertLogs(level="DEBUG") as log_output:
            setup_global_logger(logging.DEBUG)
            logging.info("Info Message")

        # Make assertions on the log format
        self.assertEqual(
            log_output.output,
            [
                "[2022-01-01 00:00:00]"
                "[root][INFO]"
                "[MainThread]"
                "[test_logger.py:66] - "
                "Info Message"
            ],
        )

    @freeze_time("2022-01-01 00:00:00 UTC")
    async def test_db_logger_writes_without_batching(self):
        """
        Log lines used to sit in a buffer until 100 had piled up. They now
        go to the writer thread as they are emitted, so a flush is all it
        takes to see them.
        """
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                logging.info("Info Message")
                self.assert_number_of_logging(
                    1, conn, should_flush_logger=True
                )

                for _ in range(0, 200):
                    logging.info("Info Message")

                self.assert_number_of_logging(
                    201, conn, should_flush_logger=True
                )

    async def test_db_logger_exceed_wait_time(self):
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                # Verify tables in DB after certain time has passed
                logging.info("Info Message")
                await asyncio.sleep(1.01)

                self.assert_number_of_logging(1, conn)

                # Verify tables grows after more logging and wait time
                logging.warning("Warning Message")
                await asyncio.sleep(1.01)

                self.assert_number_of_logging(2, conn)

    async def test_db_logger_flush_with_no_logging(self):
        """
        Makes sure that the application could gracefully shut down even when
        no logging is written to the database.
        """
        log_table_exists_query = (
            f"SELECT name FROM sqlite_master "
            f"WHERE type='table' AND name='logs';"
        )
        with self.assertLogs(level="INFO"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                self.assert_number_of_logging(
                    0, conn, should_flush_logger=True
                )

                # Flush after logging will write to database
                logging.info("Info Message")

                self.assert_number_of_logging(
                    1, conn, should_flush_logger=True
                )

    async def test_db_logger_widens_an_existing_table(self):
        """
        A logs table recorded by an older build has fewer columns than a log
        record carries. The missing ones are added rather than treated as a
        failure.
        """
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY)")

        with self.assertLogs(level="INFO"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            logging.info("Info Message")
            for handler in logging.getLogger().handlers:
                handler.flush()

        with closing(sqlite3.connect(self.database_filepath)) as conn:
            df = pd.read_sql_query("SELECT * FROM logs", con=conn)

        self.assertEqual(1, len(df))
        self.assertIn("id", df.columns)
        self.assertIn("msg", df.columns)
        self.assertIn("Info Message", df["msg"][0])

    async def test_db_logger_reports_write_failure(self):
        """
        The write happens on the writer's own thread, so a failure has to
        surface when the handler is flushed.
        """
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute("CREATE TABLE logs (required NOT NULL)")

        with self.assertLogs(level="INFO"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            logging.info("Info Message")

            with self.assertRaises(sqlite3.IntegrityError):
                for handler in logging.getLogger().handlers:
                    handler.flush()

    async def test_db_logger_ignore_debug_logging(self):
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                # Debugging logging will be ignored
                logging.debug("Debug Message")
                self.assert_number_of_logging(
                    0, conn, should_flush_logger=True
                )
                # Info/Warn/Error logging will be recorded
                logging.info("Info Message")
                self.assert_number_of_logging(
                    1, conn, should_flush_logger=True
                )
                # Info/Warn/Error logging will be recorded
                logging.warning("Warn Message")
                self.assert_number_of_logging(
                    2, conn, should_flush_logger=True
                )
                # Info/Warn/Error logging will be recorded
                logging.error("Error Message")
                self.assert_number_of_logging(
                    3, conn, should_flush_logger=True
                )

    async def test_db_logger_thread_safety(self):
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            # Number of threads
            num_threads = 100

            # Messages to log
            messages = [f"Message {i}" for i in range(num_threads)]

            def worker(message):
                logging.info(
                    f"Thread {threading.current_thread().name}: {message}"
                )
                for log_handler in logging.getLogger().handlers:
                    log_handler.flush()

            # Execute worker function concurrently using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                executor.map(worker, messages)

            # Ensure log messages were captured correctly
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                self.assert_number_of_logging(
                    num_threads, conn, should_flush_logger=True
                )
