import asyncio
import unittest

from crypto_trading_engine.core.health_monitor.heartbeat import (
    Heartbeater,
    HeartbeatLevel,
    Heartbeat,
)


class HeartbeatTestSubscriber:
    def __init__(self):
        self.all_issues = {}

    def on_heartbeat(self, sender: str, heartbeat: Heartbeater):
        if sender in self.all_issues:
            self.all_issues[sender].append(heartbeat)
        else:
            self.all_issues[sender] = [heartbeat]


class TestHeartbeater(unittest.IsolatedAsyncioTestCase):
    async def test_sort_heartbeat(self):
        heartbeats = [
            Heartbeat(HeartbeatLevel.WARN, "Hello", 0),
            Heartbeat(HeartbeatLevel.NORMAL, "", 1),
        ]
        heartbeats.sort()

        assert (
            str(heartbeats[0])
            == "Heartbeat: level=HeartbeatLevel.NORMAL, message=None, report_time=1"
        )
        assert (
            str(heartbeats[1])
            == "Heartbeat: level=HeartbeatLevel.WARN, message=Hello, report_time=0"
        )

    async def test_default_heartbeat(self):
        name = "ABC"
        interval_in_seconds = 0.01
        heartbeater = Heartbeater(name, interval_in_seconds)

        assert not heartbeater.heartbeat_signal().is_muted
        assert not heartbeater.heartbeat_signal().receivers

        subscriber = HeartbeatTestSubscriber()
        heartbeater.heartbeat_signal().connect(subscriber.on_heartbeat)

        await asyncio.sleep(interval_in_seconds)
        assert len(subscriber.all_issues) > 0
        assert len(subscriber.all_issues[name]) > 0
        assert subscriber.all_issues[name][-1].level == HeartbeatLevel.NORMAL
        assert subscriber.all_issues[name][-1].message == ""

    async def test_add_and_remove_issues(self):
        name = "ABC"
        interval_in_seconds = 0.01
        heartbeater = Heartbeater(name, interval_in_seconds)
        heartbeater.add_issue(HeartbeatLevel.WARN, "Pay Attention!")

        subscriber = HeartbeatTestSubscriber()
        heartbeater.heartbeat_signal().connect(subscriber.on_heartbeat)

        await asyncio.sleep(interval_in_seconds)
        assert len(subscriber.all_issues) > 0
        assert len(subscriber.all_issues[name]) > 0
        assert subscriber.all_issues[name][-1].level == HeartbeatLevel.WARN
        assert subscriber.all_issues[name][-1].message == "Pay Attention!"

        heartbeater.add_issue(HeartbeatLevel.WARN, "Pay Attention 2nd Time!")

        await asyncio.sleep(interval_in_seconds)
        assert subscriber.all_issues[name][-1].level == HeartbeatLevel.WARN
        assert (
            subscriber.all_issues[name][-1].message
            == "Pay Attention 2nd Time!"
        )

        heartbeater.add_issue(HeartbeatLevel.ERROR, "Pay Attention 3rd Time!")

        await asyncio.sleep(interval_in_seconds)
        assert subscriber.all_issues[name][-1].level == HeartbeatLevel.ERROR
        assert (
            subscriber.all_issues[name][-1].message
            == "Pay Attention 3rd Time!"
        )

        heartbeater.remove_issue("Pay Attention!")
        heartbeater.remove_issue("Pay Attention 2nd Time!")
        heartbeater.remove_issue("Pay Attention 3rd Time!")

        await asyncio.sleep(interval_in_seconds)
        assert len(subscriber.all_issues) > 0
        assert len(subscriber.all_issues[name]) > 0
        assert subscriber.all_issues[name][-1].level == HeartbeatLevel.NORMAL
        assert subscriber.all_issues[name][-1].message == ""
