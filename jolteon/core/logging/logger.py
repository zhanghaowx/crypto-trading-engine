# Create a custom formatter
import logging


class SmartFormatter(logging.Formatter):
    def format(self, record):
        record.msg = (
            f"[{record.name}]"
            f"[{record.levelname}]"
            f"[{record.filename}:{record.lineno}]"
            f" - {record.msg}"
        )
        return super().format(record)


def setup_global_logger(log_level, logfile_name: str):
    # Set the custom formatter for the root logger using basicConfig
    logging.basicConfig(
        level=log_level,
        format="",
        handlers=[logging.FileHandler(logfile_name)],
    )
    formatter = SmartFormatter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
