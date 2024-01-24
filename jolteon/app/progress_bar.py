import asyncio
import io
import sys
from datetime import datetime

from jolteon.core.time.time_manager import time_manager


class ProgressBar:
    def __init__(self, start_time: datetime, end_time: datetime):
        self._start_time = start_time
        self._end_time = end_time
        self._buffer = io.StringIO()
        self._sys_stdout = sys.stdout
        self._task = None

    def start(self):
        # Buffer any output to stdout until progress bar finishes
        async def buffer_sys_stdout():
            sys.stdout = self._buffer

        asyncio.create_task(buffer_sys_stdout())
        self._task = asyncio.create_task(self._update())

    def stop(self):
        assert self._task
        self._task.cancel()
        self._print_progress_bar(1.0)
        self._sys_stdout.write("\n")

        # Restore stdout
        sys.stdout = sys.__stdout__
        buffered_content = self._buffer.getvalue()
        self._buffer.close()
        sys.stdout.write(buffered_content)

    async def _update(self):
        percentage = self.calculate_percentage()
        while percentage <= 1.0:
            percentage = self.calculate_percentage()
            self._print_progress_bar(percentage)
            await asyncio.sleep(1)

    def calculate_percentage(self):
        now = time_manager().now()
        percentage = (now - self._start_time).total_seconds() / (
            self._end_time - self._start_time
        ).total_seconds()
        return percentage

    def _print_progress_bar(
        self,
        percentage: float,
        prefix="Progress:",
        suffix="",
        length=50,
        fill="█",
    ):
        percent = "{0:.1f}".format(100 * percentage)
        filled_length = int(length * percentage)
        bar = fill * filled_length + "-" * (length - filled_length)
        self._sys_stdout.write(f"\r{prefix} |{bar}| {percent}% {suffix}")
        self._sys_stdout.flush()
