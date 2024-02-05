# Create a custom formatter
import asyncio
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

import pandas as pd


class SQLiteHandler(logging.Handler):
    """
    Collects log lines and write to a SQLite database.
    """

    @dataclass
    class LogEntry:
        id: int
        level: str
        recorder: str
        thread: str
        filename: str
        line_number: int
        message: str
        created_at: float

    def __init__(
        self, db_path: str, batch_size: int = 100, delay_seconds: int = 1
    ):
        """
        Initializes the SQLite handler to process log lines and save into a
        SQLite database
        Args:
            db_path: Path to the SQLite database
            batch_size: Size of the batch to trigger a write operation to the
                        SQLite database
        """
        super(SQLiteHandler, self).__init__()
        self._db_path = db_path
        self._batch_size = batch_size
        self._delay_seconds = delay_seconds
        self._buffer = list[dict]()
        self._table_name = "logs"

        assert self._batch_size > 0

    def emit(self, record):
        self._buffer.append(record.__dict__)

        if len(self._buffer) == 1:
            asyncio.create_task(self.delayed_flush(delay=self._delay_seconds))

        if len(self._buffer) > self._batch_size:
            self.flush()

    def flush(self):
        with closing(sqlite3.connect(self._db_path)) as conn:
            if not self._buffer:
                return

            try:
                df = pd.DataFrame(self._buffer)
                df.map(str).to_sql(
                    name=self._table_name,
                    con=conn,
                    if_exists="append",
                    index=False,
                )
            except sqlite3.OperationalError as e:
                raise sqlite3.OperationalError(
                    f"Logger fails to save to table {self._table_name} "
                    f"with shape {df.shape}: {e}"
                )
            finally:
                self._buffer.clear()

    async def delayed_flush(self, delay: float):
        await asyncio.sleep(delay)
        self.flush()


class SmartFormatter(logging.Formatter):
    def format(self, record):
        record.msg = (
            f"[{datetime.fromtimestamp(record.created)}]"
            f"[{record.name}]"
            f"[{record.levelname}]"
            f"[{record.threadName}]"
            f"[{record.filename}:{record.lineno}]"
            f" - {record.msg}"
        )
        return super().format(record)


def setup_global_logger(
    log_level, logfile_name: str = "", logfile_db: str = ""
):
    handlers = list[logging.Handler]()
    if logfile_name:
        handlers.append(logging.FileHandler(logfile_name))
    else:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(level=log_level, handlers=handlers)

    # Set the custom formatter for the root logger using basicConfig
    formatter = SmartFormatter()
    root_logger = logging.getLogger()

    # For some reason, custom handlers must be added outside of
    # basic configuration
    database_logger = SQLiteHandler(logfile_db)
    # To avoid writing too much data into database, we will limit the lowest
    # log level
    if log_level < logging.INFO:
        database_logger.setLevel(logging.INFO)
    else:
        database_logger.setLevel(log_level)
    root_logger.addHandler(database_logger)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
