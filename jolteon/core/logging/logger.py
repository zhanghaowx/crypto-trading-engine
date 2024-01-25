# Create a custom formatter
import logging
from datetime import datetime


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


def setup_global_logger(log_level, logfile_name: str = ""):
    # Set the custom formatter for the root logger using basicConfig
    if logfile_name:
        logging.basicConfig(
            level=log_level,
            format="",
            handlers=[logging.FileHandler(logfile_name)],
        )
    else:
        logging.basicConfig(
            level=log_level,
            format="",
            handlers=[logging.StreamHandler()],
        )

    formatter = SmartFormatter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
