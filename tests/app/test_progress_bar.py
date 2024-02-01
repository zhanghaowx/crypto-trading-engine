import asyncio
import io
import unittest
from datetime import timedelta, datetime
from unittest.mock import patch

import pytz

from jolteon.app.progress_bar import ProgressBar
from jolteon.core.time.time_manager import time_manager


class TestProgressBar(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.start_time = datetime(
            year=2024,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=pytz.utc,
        )
        self.end_time = self.start_time + timedelta(seconds=10)
        self.setup_fake_time()

    async def asyncTearDown(self):
        self.reset_fake_time()

    def setup_fake_time(self):
        time_manager().claim_admin(self)
        time_manager().use_fake_time(
            self.start_time + timedelta(seconds=2), admin=self
        )

    @staticmethod
    def reset_fake_time():
        time_manager().force_reset()

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_start_stop_progress_bar(self, mock_stdout):
        progress_bar = ProgressBar(self.start_time, self.end_time)
        self.assertEqual(mock_stdout, progress_bar._sys_stdout)

        progress_bar.start()
        await asyncio.sleep(0)
        await asyncio.sleep(progress_bar.UPDATE_INTERVAL + 0.01)

        # Validate the printed content
        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertIn(
            "Progress: |██████████--", printed_content
        )  # Adjust based on the expected progress
        self.assertIn("--| 20.0%", printed_content)

        # Progress bard adjusted to pre-defined percentage after being stopped
        progress_bar.stop(stop_at=1.0)

        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertIn(
            "Progress: "
            "|██████████████████████████████████████████████████|",
            printed_content,
        )  # Adjust based on the expected progress
        self.assertIn("██| 100.0%", printed_content)

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_buffered_stdout_during_process(self, mock_stdout):
        progress_bar = ProgressBar(self.start_time, self.end_time)
        self.assertEqual(mock_stdout, progress_bar._sys_stdout)

        progress_bar.start()
        await asyncio.sleep(0)
        await asyncio.sleep(progress_bar.UPDATE_INTERVAL + 0.01)

        print("Hello World")

        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertNotIn("Hello World", printed_content)

        progress_bar.stop(stop_at=1.0)

        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertIn("Hello World", printed_content)

        # The print output will no longer be buffered after progress bar is
        # stopped
        print("The End")
        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("The End", printed_content)
