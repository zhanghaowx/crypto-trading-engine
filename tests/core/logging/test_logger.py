import logging
import unittest

from freezegun import freeze_time

from jolteon.core.logging.logger import setup_global_logger


class TestLogging(unittest.TestCase):
    @freeze_time("2022-01-01 00:00:00 UTC")
    def test_perform_logging_format(self):
        # Perform the logging and capture the log output
        with self.assertLogs(level="DEBUG") as log_output:
            setup_global_logger(logging.DEBUG)
            logging.info("Info Message")

        # Make assertions on the log format
        print(log_output.output)
        self.assertEqual(
            log_output.output,
            [
                "[2022-01-01 00:00:00]"
                "[root][INFO]"
                "[MainThread]"
                "[test_logger.py:15] - "
                "Info Message"
            ],
        )
