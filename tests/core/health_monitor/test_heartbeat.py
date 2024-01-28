import asyncio
import unittest

from blinker import ANY

from jolteon.core.health_monitor.heartbeat import (
    Heartbeater,
    HeartbeatLevel,
    Heartbeat,
)
from jolteon.core.time.time_manager import time_manager


class HeartbeatTestSubscriber:
    def __init__(self):
        self.all_issues = {}

    def on_heartbeat(self, _: str, heartbeat: Heartbeat):
        if heartbeat.sender in self.all_issues:
            self.all_issues[heartbeat.sender].append(heartbeat)
        else:
            self.all_issues[heartbeat.sender] = [heartbeat]


class TestHeartbeater(unittest.IsolatedAsyncioTestCase):
    async def test_sort_heartbeat(self):
        heartbeats = [
            Heartbeat(
                level=HeartbeatLevel.WARN, message="Hello", report_time=1
            ),
            Heartbeat(level=HeartbeatLevel.NORMAL, message="", report_time=2),
        ]
        heartbeats.sort()

        self.assertEqual(
            str(heartbeats[0]),
            "Heartbeat: level=HeartbeatLevel.NORMAL, sender=None, message=None, "
            "report_time=2",
        )
        self.assertEqual(
            str(heartbeats[1]),
            "Heartbeat: level=HeartbeatLevel.WARN, sender=None, message=Hello, "
            "report_time=1",
        )

    async def test_default_heartbeat(self):
        name = "ABC"
        interval_in_seconds = 0.01
        heartbeater = Heartbeater(name, interval_in_seconds)

        self.assertFalse(heartbeater.heartbeat_signal().is_muted)
        self.assertFalse(heartbeater.heartbeat_signal().has_receivers_for(ANY))

        subscriber = HeartbeatTestSubscriber()
        heartbeater.heartbeat_signal().connect(subscriber.on_heartbeat)

        self.assertEqual(len(subscriber.all_issues), 0)
        await asyncio.sleep(interval_in_seconds)
        self.assertGreater(len(subscriber.all_issues), 0)

        last_heartbeat = subscriber.all_issues[name][-1]
        self.assertGreater(len(subscriber.all_issues[name]), 0)
        self.assertEqual(last_heartbeat.level, HeartbeatLevel.NORMAL)
        self.assertEqual(last_heartbeat.message, "")
        self.assertGreaterEqual(
            interval_in_seconds,
            (
                last_heartbeat.report_time - time_manager().now()
            ).total_seconds(),
        )

    async def test_send_heartbeat(self):
        name = "ABC"
        interval_in_seconds = 0  # Disable automatically heartbeating
        heartbeater = Heartbeater(name, interval_in_seconds)

        self.assertFalse(heartbeater.heartbeat_signal().is_muted)
        self.assertFalse(heartbeater.heartbeat_signal().receivers)

        subscriber = HeartbeatTestSubscriber()
        heartbeater.heartbeat_signal().connect(subscriber.on_heartbeat)

        heartbeater.send_heartbeat()
        self.assertGreater(len(subscriber.all_issues), 0)
        self.assertGreater(len(subscriber.all_issues[name]), 0)
        self.assertEqual(
            subscriber.all_issues[name][-1].level, HeartbeatLevel.NORMAL
        )
        self.assertEqual(subscriber.all_issues[name][-1].message, "")

    async def test_add_and_remove_issues(self):
        name = "ABC"
        interval_in_seconds = 0.01
        heartbeater = Heartbeater(name, interval_in_seconds)
        heartbeater.add_issue(HeartbeatLevel.WARN, "Pay Attention!")

        subscriber = HeartbeatTestSubscriber()
        heartbeater.heartbeat_signal().connect(subscriber.on_heartbeat)

        await asyncio.sleep(interval_in_seconds)
        self.assertGreater(len(subscriber.all_issues), 0)
        self.assertGreater(len(subscriber.all_issues[name]), 0)
        self.assertEqual(
            subscriber.all_issues[name][-1].level, HeartbeatLevel.WARN
        )
        self.assertEqual(
            subscriber.all_issues[name][-1].message, "Pay Attention!"
        )

        heartbeater.add_issue(HeartbeatLevel.WARN, "Pay Attention 2nd Time!")

        await asyncio.sleep(interval_in_seconds)
        self.assertEqual(
            subscriber.all_issues[name][-1].level, HeartbeatLevel.WARN
        )
        self.assertEqual(
            subscriber.all_issues[name][-1].message, "Pay Attention 2nd Time!"
        )

        heartbeater.add_issue(HeartbeatLevel.ERROR, "Pay Attention 3rd Time!")

        await asyncio.sleep(interval_in_seconds)
        self.assertEqual(
            subscriber.all_issues[name][-1].level, HeartbeatLevel.ERROR
        )
        self.assertEqual(
            subscriber.all_issues[name][-1].message, "Pay Attention 3rd Time!"
        )

        heartbeater.remove_issue("Pay Attention!")
        heartbeater.remove_issue("Pay Attention 2nd Time!")
        heartbeater.remove_issue("Pay Attention 3rd Time!")

        await asyncio.sleep(interval_in_seconds)
        self.assertGreater(len(subscriber.all_issues), 0)
        self.assertGreater(len(subscriber.all_issues[name]), 0)
        self.assertEqual(
            subscriber.all_issues[name][-1].level, HeartbeatLevel.NORMAL
        )
        self.assertEqual(subscriber.all_issues[name][-1].message, "")
