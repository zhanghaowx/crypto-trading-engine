# Create a custom formatter
import logging
import logging.handlers
from datetime import datetime

from jolteon.core.sqlite_writer import SQLiteWriter

_MAX_LOGFILE_BYTES = 10 * 1024 * 1024
_LOGFILE_BACKUP_COUNT = 5

_MAX_LOG_ROWS = 200_000
_PRUNE_INTERVAL = 1_000


class SQLiteHandler(logging.Handler):
    """
    Writes log lines to a SQLite database.

    Logging happens on the market data thread as well as the engine's event
    loop, so `emit` must not touch SQLite itself: it hands the record to a
    `SQLiteWriter`, which owns the connection and does the write, and later
    the pruning, on its own thread.
    """

    def __init__(self, db_path: str):
        """
        Initializes the SQLite handler to process log lines and save into a
        SQLite database
        Args:
            db_path: Path to the SQLite database
        """
        super(SQLiteHandler, self).__init__()
        self._db_path = db_path
        self._writer = SQLiteWriter(db_path)
        self._table_name = "logs"
        self._emitted = 0

    def emit(self, record):
        # Values are stringified because a LogRecord carries arbitrary
        # objects (`args`, `exc_info`) that SQLite cannot store.
        self._writer.put(
            self._table_name,
            {key: str(value) for key, value in record.__dict__.items()},
        )

        self._emitted += 1
        if self._emitted % _PRUNE_INTERVAL == 0:
            self._writer.prune(self._table_name, _MAX_LOG_ROWS)

    def flush(self):
        """Block until every record emitted so far is in the database."""
        self._writer.flush()

    def close(self):
        self._writer.close()
        super().close()


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
        handlers.append(
            logging.handlers.RotatingFileHandler(
                logfile_name,
                maxBytes=_MAX_LOGFILE_BYTES,
                backupCount=_LOGFILE_BACKUP_COUNT,
            )
        )
    else:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(level=log_level, handlers=handlers)

    # Set the custom formatter for the root logger using basicConfig
    formatter = SmartFormatter()
    root_logger = logging.getLogger()

    # Each SQLiteHandler owns a writer thread and a connection, so drop any
    # handler left over from an earlier call rather than accumulating both.
    for existing in list(root_logger.handlers):
        if isinstance(existing, SQLiteHandler):
            root_logger.removeHandler(existing)
            existing.close()

    # For some reason, custom handlers must be added outside of
    # basic configuration
    if logfile_db:
        database_logger = SQLiteHandler(logfile_db)
        # To avoid writing too much data into database, we will limit the
        # lowest log level
        if log_level < logging.INFO:
            database_logger.setLevel(logging.INFO)
        else:
            database_logger.setLevel(log_level)
        root_logger.addHandler(database_logger)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
