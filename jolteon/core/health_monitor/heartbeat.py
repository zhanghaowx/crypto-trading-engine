import asyncio
import functools
import logging
from datetime import datetime
from enum import Enum
from typing import Union

from jolteon.core.event.signal import signal
from jolteon.core.time.time_manager import time_manager


def starts_heartbeating(func):
    """Marks a Heartbeater's driving coroutine: starts its periodic
    heartbeat, on the caller's running loop, before running it."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        self.start_heartbeating()
        return await func(self, *args, **kwargs)

    return wrapper


class HeartbeatLevel(Enum):
    NORMAL = 1  # Everything is working properly
    WARN = 2  # Something is wrong, but it could be recovered or tolerated
    ERROR = 3  # Something is wrong, and requires immediate inspection
    CRITICAL = 4  # Severe error happens, system must be terminated


class Heartbeat:
    def __init__(
        self,
        level: HeartbeatLevel = HeartbeatLevel.NORMAL,
        sender: str = "",
        message: str = "",
        report_time: Union[datetime, None] = None,
    ):
        """
        A heartbeat is a message emitted by an observable to notify the
        monitoring service about the status of itself.

        Args:
            level: The severity is this issue.
            message: Additional details about this issue.
        """
        self.level = level
        self.sender = sender
        self.message = message
        self.report_time = report_time if report_time else time_manager().now()
        assert (self.level == HeartbeatLevel.NORMAL) or (
            len(self.message) > 0
        ), (
            f"Please add additional message if the heartbeat level is "
            f"{self.level}"
        )

    def __lt__(self, other):
        if self.level.value < other.level.value:
            return True
        elif self.level.value == other.level.value:
            return self.report_time < other.report_time

        return False

    def __repr__(self):
        return (
            f"Heartbeat: "
            f"level={self.level}, "
            f"sender={self.sender if len(self.sender) > 0 else 'None'}, "
            f"message={self.message if len(self.message) > 0 else 'None'}, "
            f"report_time={self.report_time}"
        )


class Heartbeater:
    def __init__(
        self, name: str = "anonymous", interval_in_seconds: float = 5
    ):
        """
        *Heartbeater* is the component that sends *Heartbeat* messages to
        *HeartbeatMonitor* for issue reporting.

        *Heartbeat* is a type of health monitor method that asks components
        to send a special type of message (heartbeat) at a fixed internal.
        This could be used to monitor if all your dependent components are
        working properly.

        Components may choose different ways to send heartbeats. For example,
        a market data component might choose to only send a heartbeat when
        receiving a channel heartbeat from the exchange. Another component
        might choose to send a heartbeat every 1 second.

        Args:
            name: Name of the component who sends heartbeats
            interval_in_seconds: Interval in seconds to send heartbeats
            periodically. Use 0 to disable the schedule and send heartbeats
            manually.
        """
        self._name = name
        self._interval_in_seconds = interval_in_seconds
        self._heartbeat_signal = signal("heartbeat")
        self._issues = [
            Heartbeat(level=HeartbeatLevel.NORMAL, sender=self._name)
        ]
        self._heartbeating_task: Union[asyncio.Task, None] = None

    def __del__(self):
        task = self._heartbeating_task
        if task and not task.get_loop().is_closed():
            task.cancel()

    def start_heartbeating(self):
        """
        Starts sending heartbeats periodically on the caller's running
        event loop. Idempotent - only the first call has any effect.

        Call this from the coroutine that does the component's real
        recurring work, not from __init__, so a hang in that loop stalls
        its own heartbeats instead of heartbeats riding on an unrelated
        loop. `@subscribe`-decorated handlers call this automatically.
        """
        if self._heartbeating_task is None and self._interval_in_seconds > 0:
            self._heartbeating_task = asyncio.get_running_loop().create_task(
                self._run_heartbeating_loop()
            )

    async def _run_heartbeating_loop(self):
        while True:
            self.send_heartbeat()
            await asyncio.sleep(self._interval_in_seconds)

    def heartbeat_signal(self):
        """
        Returns: The heartbeat signal to send periodic heartbeat messages
        """
        return self._heartbeat_signal

    def add_issue(self, level: HeartbeatLevel, message: str):
        """
        Add an issue to the issue list.

        Args:
            level: The severity is this issue.
            message: Additional details about this issue.

        Returns:
            Index of the newly inserted issue. This index could be used to
            clear the issue later on.
        """
        assert level.value > HeartbeatLevel.NORMAL.value, (
            "Please report only severe issues that exceed "
            "the normal severity level!"
        )
        assert len(message) > 0, "Please add details to your issue"
        self._issues.append(
            Heartbeat(level=level, message=message, sender=self._name)
        )
        self._issues.sort()
        return len(self._issues) - 1

    def remove_issue(self, message: str):
        """
        Remove an issue from the issue list when it is back to normal.

        Args:
            message: Additional details about this issue

        Returns:
            None
        """
        assert len(message) > 0, "Cannot remove the NORMAL heartbeat!"
        self._issues = [x for x in self._issues if x.message != message]
        self._issues.sort()

    def send_heartbeat(self):
        """
        Manually sends a heartbeat out

        Returns:
            None
        """
        assert len(self._issues) > 0, (
            "Please have at least one Heartbeat in the list "
            "before sending it out!"
        )

        last_heartbeat = self._issues[-1]
        last_heartbeat.report_time = time_manager().now()

        self._heartbeat_signal.send(
            self._heartbeat_signal, heartbeat=last_heartbeat
        )
        logging.debug(f"Sent {last_heartbeat}")
