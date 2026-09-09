import asyncio
import unittest

from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.health_monitor.heartbeat_monitor import (
    HeartbeatMonitor,
)


class TestHeartbeatMonitor(unittest.IsolatedAsyncioTestCase):
    async def test_stale_heartbeat(self):
        heartbeater = Heartbeater("ABC", 0)

        # Kept well above typical OS timer resolution (e.g. Windows'
        # ~15.6ms default tick) so the periodic zombie-detection task
        # reliably gets to run within the sleep window below.
        time_out_in_seconds = 0.1
        monitor = HeartbeatMonitor(time_out_in_seconds)
        heartbeater.heartbeat_signal().connect(monitor.on_heartbeat)

        heartbeater.send_heartbeat()
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertFalse(monitor.all_heartbeats["ABC"].is_zombie())

        await asyncio.sleep(time_out_in_seconds * 3)
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertTrue(monitor.all_heartbeats["ABC"].is_zombie())

        heartbeater.send_heartbeat()
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertFalse(monitor.all_heartbeats["ABC"].is_zombie())
