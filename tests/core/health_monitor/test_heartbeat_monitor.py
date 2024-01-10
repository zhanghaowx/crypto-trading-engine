import asyncio
import unittest

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.health_monitor.heartbeat_monitor import (
    HeartbeatMonitor,
)


class TestHeartbeatMonitor(unittest.IsolatedAsyncioTestCase):
    async def test_stale_heartbeat(self):
        heartbeater = Heartbeater("ABC", 0)

        time_out_in_seconds = 0.01
        monitor = HeartbeatMonitor(time_out_in_seconds)
        heartbeater.heartbeat_signal().connect(monitor.on_heartbeat)

        heartbeater.send_heartbeat()
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertFalse(monitor.all_heartbeats["ABC"].is_zombie())

        await asyncio.sleep(time_out_in_seconds * 2)
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertTrue(monitor.all_heartbeats["ABC"].is_zombie())

        heartbeater.send_heartbeat()
        self.assertTrue("ABC" in monitor.all_heartbeats)
        self.assertFalse(monitor.all_heartbeats["ABC"].is_zombie())
