import asyncio
import io
import sys
from datetime import datetime, timezone

import pytz

from jolteon.core.time.time_manager import time_manager


class ProgressBar:
    UPDATE_INTERVAL = 0.1

    """
    Displays a progress bar based on current time elapsed since the start.
    User have to set a start time and an end time to calculate the elapsed
    percentage.
    """

    def __init__(self, start_time: datetime, end_time: datetime):
        self._start_time = start_time
        self._end_time = end_time
        self._buffer = io.StringIO()
        self._sys_stdout = sys.stdout
        self._buffer_task = None
        self._update_task = None

        assert (
            self._start_time.tzinfo == pytz.utc
            or self._start_time.tzinfo == timezone.utc
        )
        assert (
            self._end_time.tzinfo == pytz.utc
            or self._end_time.tzinfo == timezone.utc
        )

    def start(self):
        # Buffer any output to stdout until progress bar finishes
        async def buffer_sys_stdout():
            sys.stdout = self._buffer

        self._buffer_task = asyncio.create_task(buffer_sys_stdout())
        self._update_task = asyncio.create_task(self._update())

    def stop(self, stop_at: float = 1.0):
        assert self._update_task
        self._update_task.cancel()

        assert self._buffer_task
        self._buffer_task.cancel()

        self._print_progress_bar(stop_at)
        self._sys_stdout.write("\n")

        # Restore stdout
        sys.stdout = self._sys_stdout
        buffered_content = self._buffer.getvalue()
        self._buffer.close()
        self._sys_stdout.write(buffered_content)

    async def _update(self):
        # Avoid using "while percentage <= 1.0" because this check might be
        # performed before mock time is set properly
        while True:
            await asyncio.sleep(ProgressBar.UPDATE_INTERVAL)
            percentage = self.calculate_percentage()
            self._print_progress_bar(percentage)

    def calculate_percentage(self):
        now = time_manager().now()
        total_seconds = (self._end_time - self._start_time).total_seconds()
        elapsed_seconds = (now - self._start_time).total_seconds()
        return elapsed_seconds / max(1e-10, total_seconds)

    def _print_progress_bar(
        self,
        percentage: float,
        prefix="Progress:",
        suffix="",
        length=50,
        fill="█",
    ):
        percentage = min(1.0, percentage)
        percent = "{0:.1f}".format(100 * percentage)
        filled_length = int(length * percentage)
        bar = fill * filled_length + "-" * (length - filled_length)
        self._sys_stdout.write(f"\r{prefix} |{bar}| {percent}% {suffix}")
        self._sys_stdout.flush()
