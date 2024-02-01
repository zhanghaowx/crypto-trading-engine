import asyncio
import logging
import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing

import pandas as pd
from freezegun import freeze_time

from jolteon.core.logging.logger import setup_global_logger


class TestLogging(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )

    def tearDown(self):
        if os.path.exists(self.database_filepath):
            os.remove(self.database_filepath)

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
                "[test_logger.py:31] - "
                "Info Message"
            ],
        )

    @freeze_time("2022-01-01 00:00:00 UTC")
    async def test_db_logger_exceed_batch_size(self):
        log_table_exists_query = (
            f"SELECT name FROM sqlite_master "
            f"WHERE type='table' AND name='logs';"
        )
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                # Verify tables NOT in DB before buffer is full
                for i in range(0, 100):
                    logging.info("Info Message")

                    df = pd.read_sql_query(log_table_exists_query, con=conn)
                    self.assertEqual(len(df), 0)

                # Verify tables in DB after buffer is full
                logging.info("Info Message")

                df = pd.read_sql_query(log_table_exists_query, con=conn)
                self.assertEqual(len(df), 1)

                df = pd.read_sql_query("SELECT * FROM logs", con=conn)
                self.assertEqual(len(df), 101)

    async def test_db_logger_exceed_wait_time(self):
        log_table_exists_query = (
            f"SELECT name FROM sqlite_master "
            f"WHERE type='table' AND name='logs';"
        )
        with self.assertLogs(level="DEBUG"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )
            with closing(sqlite3.connect(self.database_filepath)) as conn:
                logging.info("Info Message")

                # Verify tables in DB after buffer is full
                await asyncio.sleep(1.001)

                df = pd.read_sql_query(log_table_exists_query, con=conn)
                self.assertEqual(len(df), 1)

                df = pd.read_sql_query("SELECT * FROM logs", con=conn)
                self.assertEqual(len(df), 1)

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
                for handler in logging.getLogger().handlers:
                    handler.flush()

                df = pd.read_sql_query(log_table_exists_query, con=conn)
                self.assertEqual(len(df), 0)

                # Flush after logging will write to database
                logging.info("Info Message")

                for handler in logging.getLogger().handlers:
                    handler.flush()

                df = pd.read_sql_query(log_table_exists_query, con=conn)
                self.assertEqual(len(df), 1)

    async def test_db_logger_exception(self):
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY)")

        with self.assertLogs(level="INFO"):
            setup_global_logger(
                logging.DEBUG, logfile_db=self.database_filepath
            )

            # Flush after logging will write to database
            logging.info("Info Message")

            with self.assertRaises(sqlite3.OperationalError):
                for handler in logging.getLogger().handlers:
                    handler.flush()
