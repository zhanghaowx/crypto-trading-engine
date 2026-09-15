import threading
from enum import StrEnum
from typing import Callable


class HealthState(StrEnum):
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def can_trade(self) -> bool:
        return self in (HealthState.HEALTHY, HealthState.WARNING)


class Health:
    """Current in-memory health of one service."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._state = HealthState.INITIALIZING
        self._listeners: list[Callable[[HealthState], None]] = []
        self._lock = threading.RLock()

    @property
    def state(self) -> HealthState:
        with self._lock:
            return self._state

    @property
    def is_healthy(self) -> bool:
        return self.state == HealthState.HEALTHY

    @property
    def can_trade(self) -> bool:
        return self.state.can_trade

    def mark_initializing(self) -> None:
        self._set(HealthState.INITIALIZING)

    def mark_healthy(self) -> None:
        self._set(HealthState.HEALTHY)

    def mark_warning(self) -> None:
        self._set(HealthState.WARNING)

    def mark_critical(self) -> None:
        self._set(HealthState.CRITICAL)

    def add_listener(self, listener: Callable[[HealthState], None]) -> None:
        with self._lock:
            self._listeners.append(listener)
            state = self._state
        listener(state)

    def _set(self, state: HealthState) -> None:
        with self._lock:
            if self._state == state:
                return
            self._state = state
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(state)


class HealthMonitor(Health):
    """Health that is healthy only while every dependency is healthy."""

    def __init__(self, name: str = "trading") -> None:
        super().__init__(name)
        self._dependencies: dict[str, Health] = {}

    def require(self, health: Health) -> None:
        with self._lock:
            existing = self._dependencies.get(health.name)
            assert existing is None or existing is health, (
                f"Health dependency {health.name!r} is already registered"
            )
            if existing is health:
                return
            self._dependencies[health.name] = health
        health.add_listener(lambda _: self._update())

    def run_if_can_trade(self, action: Callable[[], None]) -> bool:
        """Run an order-side action atomically with the health decision."""
        with self._lock:
            if not self.can_trade:
                return False
            action()
            return True

    def _update(self) -> None:
        with self._lock:
            states = tuple(
                dependency.state for dependency in self._dependencies.values()
            )
            if HealthState.CRITICAL in states:
                state = HealthState.CRITICAL
            elif not states or HealthState.INITIALIZING in states:
                state = HealthState.INITIALIZING
            elif HealthState.WARNING in states:
                state = HealthState.WARNING
            else:
                state = HealthState.HEALTHY
            if self._state == state:
                return
            self._state = state
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(state)
