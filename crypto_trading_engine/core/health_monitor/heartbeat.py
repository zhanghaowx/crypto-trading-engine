import asyncio

from enum import Enum
from datetime import datetime

from blinker import signal


class HeartbeatLevel(Enum):
    NORMAL = 1  # Everything is working properly
    WARN = 2  # Something is wrong, but it could be recovered or tolerated
    ERROR = 3  # Something is wrong, and requires immediate inspection
    CRITICAL = 4  # Severe error happens, system must be terminated to prevent more loss


class Heartbeat:
    def __init__(self, level: HeartbeatLevel = HeartbeatLevel.NORMAL, message: str = ""):
        """
        A heartbeat is a message emitted by an observable to notify the monitoring service about the status of itself.

        Args:
            level: The severity is this issue.
            message: Additional details about this issue.
        """
        self.level = level
        self.message = message
        self.report_time = datetime.now()
        assert (self.level == HeartbeatLevel.NORMAL) or (len(self.message) > 0), \
            f"Please add additional message if the heartbeat level is {self.level}"

    def __repr__(self):
        return (f"Heartbeat: level={self.level}, "
                f"message={self.message if len(self.message) > 0 else 'None'}, "
                f"report_time={self.report_time}")


class Heartbeater:
    """
    Heartbeat is a type of health monitor method that asks components to send a special type of message (heartbeat) at a
    fixed internal. This could be used to monitor if all your dependent components are working properly.
    Heartbeater is the component that sends Heartbeat messages to HeartbeatMonitor for issue reporting.
    """

    def __init__(self, interval_in_seconds: int):
        self._interval_in_seconds = interval_in_seconds
        self._heartbeat_signal = signal("heartbeat")
        self._issues = [Heartbeat(HeartbeatLevel.NORMAL)]
        assert self._interval_in_seconds > 0, "Please set interval_in_seconds to be a positive number in seconds!"
        assert len(self._issues) > 0, "Please put at least one Heartbeat(NORMAL, "") in the issue list!"

        asyncio.create_task(self._start_heartbeating())

    def heartbeat_signal(self):
        """
        Returns: The heartbeat signal to send periodic heartbeat messages
        """
        return self._heartbeat_signal

    def raise_issue(self, level: HeartbeatLevel = HeartbeatLevel.NORMAL, message: str = ""):
        """
        Add an issue to the issue list.

        Args:
            level: The severity is this issue.
            message: Additional details about this issue.

        Returns:
            Index of the newly inserted issue. This index could be used to clear the issue later on.
        """
        self._issues.append(Heartbeat(level, message))
        self._issues.sort(key=lambda x: (x.level, x.report_time))
        return len(self._issues) - 1

    def clear_issue(self, index: int):
        """
        Remove an issue from the issue list.

        Args:
            index: Index of the issue to be cleared

        Returns:
            None
        """
        del self._issues[index]

    async def _start_heartbeating(self):
        while True:
            self._heartbeat_signal.send('anonymous', heartbeat=self._issues[-1])
            await asyncio.sleep(self._interval_in_seconds)
