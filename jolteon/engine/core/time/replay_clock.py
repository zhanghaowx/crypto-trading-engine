"""Simulated domain deadlines, independently paced by monotonic time."""

import asyncio
import heapq
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count


@dataclass(order=True)
class Timer:
    due: float
    ordinal: int
    callback: Callable[[], None] = field(compare=False)
    cancelled: bool = field(default=False, compare=False)

    def cancel(self) -> None:
        self.cancelled = True


class ReplayClock:
    def __init__(self, start: float, on_advance: Callable[[datetime], None]):
        self.timestamp = start
        self._on_advance = on_advance
        self._timers: list[Timer] = []
        self._ordinals = count()

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, timezone.utc)

    def call_at(self, due: float, callback: Callable[[], None]) -> Timer:
        if not math.isfinite(due) or due < self.timestamp:
            raise ValueError(
                "Timer deadline must be finite and not in the past"
            )
        timer = Timer(due, next(self._ordinals), callback)
        heapq.heappush(self._timers, timer)
        return timer

    @property
    def next_deadline(self) -> float | None:
        return self._timers[0].due if self._timers else None

    def advance(self, timestamp: float) -> None:
        if not math.isfinite(timestamp) or timestamp < self.timestamp:
            raise ValueError("Simulated time cannot move backwards")
        callbacks = 0
        while self._timers and self._timers[0].due <= timestamp:
            timer = heapq.heappop(self._timers)
            if timer.due > self.timestamp:
                callbacks = 0
            self._set_time(timer.due)
            if not timer.cancelled:
                callbacks += 1
                if callbacks > 100_000:
                    raise RuntimeError("Timer loop did not make progress")
                timer.callback()
        self._set_time(timestamp)

    def _set_time(self, timestamp: float) -> None:
        self.timestamp = timestamp
        self._on_advance(self.now())

    def close(self) -> None:
        self._timers.clear()


class Playback:
    SPEEDS = {"1x": 1, "10x": 10, "24x": 24, "unbounded": None}

    def __init__(
        self, speed: str, monotonic=time.monotonic, sleep=asyncio.sleep
    ):
        if speed not in self.SPEEDS:
            raise ValueError(f"Unsupported playback speed: {speed}")
        self.multiplier = self.SPEEDS[speed]
        self._monotonic = monotonic
        self._sleep = sleep
        self._started: float | None = None
        self._origin: float | None = None
        self.max_lag_seconds = 0.0

    async def pace(self, timestamp: float) -> None:
        if self._started is None:
            self._started = self._monotonic()
            self._origin = timestamp
        if self.multiplier is None:
            await self._sleep(0)
            return
        assert self._origin is not None
        target = (timestamp - self._origin) / self.multiplier
        remaining = target - (self._monotonic() - self._started)
        self.max_lag_seconds = max(self.max_lag_seconds, -remaining)
        await self._sleep(max(0, remaining))

    async def advance(self, clock: ReplayClock, timestamp: float) -> None:
        while clock.next_deadline is not None:
            due = clock.next_deadline
            if due > timestamp:
                break
            await self.pace(due)
            clock.advance(due)
        await self.pace(timestamp)
        clock.advance(timestamp)
