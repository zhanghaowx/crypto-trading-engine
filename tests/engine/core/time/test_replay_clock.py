import asyncio

import pytest

from jolteon.engine.core.time.replay_clock import Playback, ReplayClock


def test_timers_ties_cancellation_and_quiet_intervals():
    observed = []
    clock = ReplayClock(0, lambda now: None)
    clock.call_at(2, lambda: observed.append("first"))
    clock.call_at(
        2, lambda: clock.call_at(2, lambda: observed.append("nested"))
    )
    cancelled = clock.call_at(1, lambda: observed.append("cancelled"))
    cancelled.cancel()
    clock.advance(3)
    assert observed == ["first", "nested"]
    assert clock.now().timestamp() == 3
    assert clock.next_deadline is None
    with pytest.raises(ValueError):
        clock.advance(2)
    with pytest.raises(ValueError):
        clock.call_at(float("nan"), lambda: None)
    clock.call_at(4, lambda: None)
    clock.close()
    assert clock.next_deadline is None


@pytest.mark.parametrize("speed", ["1x", "10x", "24x", "unbounded"])
def test_pacing_uses_virtual_monotonic_time(speed):
    wall = [0.0]
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        wall[0] += delay

    playback = Playback(speed, lambda: wall[0], sleep)
    clock = ReplayClock(0, lambda now: None)
    fired = []
    clock.call_at(12, lambda: fired.append(clock.timestamp))

    async def run():
        await playback.pace(0)
        await playback.advance(clock, 24)

    asyncio.run(run())
    assert fired == [12]
    assert wall[0] == (
        0 if speed == "unbounded" else 24 / Playback.SPEEDS[speed]
    )
    assert clock.timestamp == 24


def test_bad_speed_and_lag():
    with pytest.raises(ValueError):
        Playback("2x")
    wall = [0]

    async def sleep(delay):
        assert delay == 0

    playback = Playback("1x", lambda: wall[0], sleep)
    asyncio.run(playback.pace(0))
    wall[0] = 100
    asyncio.run(playback.pace(1))
    assert playback.max_lag_seconds == 99


def test_runaway_and_future_deadlines():
    clock = ReplayClock(0, lambda now: None)

    def again():
        clock.call_at(0, again)

    clock.call_at(0, again)
    with pytest.raises(RuntimeError, match="progress"):
        clock.advance(0)
    clock.close()
    clock.call_at(10, lambda: None)

    async def sleep(delay):
        pass

    asyncio.run(Playback("unbounded", sleep=sleep).advance(clock, 1))
    assert clock.next_deadline == 10


def test_zero_delay_timer_waits_for_signal_cascade():
    from jolteon.engine.core.event.signal import signal

    clock = ReplayClock(0, lambda now: None)
    observed = []
    first = signal("timer_test_first")
    nested = signal("timer_test_nested")

    def receiver(sender):
        observed.append("first")
        clock.call_at(0, lambda: observed.append("timer"))
        nested.send(nested)

    def nested_receiver(sender):
        observed.append("nested")

    first.connect(receiver)
    nested.connect(nested_receiver)
    first.send(first)
    clock.advance(0)
    assert observed == ["first", "nested", "timer"]


def test_recurring_timers_can_cross_a_long_quiet_interval():
    clock = ReplayClock(0, lambda now: None)
    count = [0]

    def tick():
        count[0] += 1
        clock.call_at(clock.timestamp + 1, tick)

    clock.call_at(1, tick)
    clock.advance(100001)
    assert count[0] == 100001
