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

    async def asyncTearDown(self):
        time_manager().force_reset()

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_progress_bar(self, mock_stdout):
        progress_bar = ProgressBar(self.start_time, self.end_time)
        progress_bar.UPDATE_INTERVAL = 0.1
        self.assertEqual(mock_stdout, progress_bar._sys_stdout)

        time_manager().claim_admin(self)
        time_manager().use_fake_time(
            self.start_time + timedelta(seconds=2), admin=self
        )

        progress_bar.start()
        await asyncio.sleep(0.1)

        # Validate the printed content
        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertIn(
            "Progress: |██████████--", printed_content
        )  # Adjust based on the expected progress
        self.assertIn(
            "--| 20.0%", printed_content
        )  # Adjust based on the expected percentage

    @patch("sys.stdout", new_callable=io.StringIO)
    async def test_buffered_stdout_during_process(self, mock_stdout):
        progress_bar = ProgressBar(self.start_time, self.end_time)
        progress_bar.UPDATE_INTERVAL = 0.1
        self.assertEqual(mock_stdout, progress_bar._sys_stdout)

        time_manager().claim_admin(self)
        time_manager().use_fake_time(
            self.start_time + timedelta(seconds=2), admin=self
        )

        progress_bar.start()
        await asyncio.sleep(0.1)

        print("Hello World")

        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Progress:", printed_content)
        self.assertNotIn("Hello World", printed_content)

        progress_bar.stop()

        printed_content = mock_stdout.getvalue().strip()
        self.assertIn("Hello World", printed_content)
        self.assertIn("Hello World", printed_content)
