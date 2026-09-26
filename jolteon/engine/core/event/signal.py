import functools
import threading
from collections import deque
from typing import Any

from blinker import NamedSignal
from blinker._utilities import make_id

_delivery = threading.local()


class Signal(NamedSignal):
    """
    Delivers an event sent from inside a receiver only after the event
    being delivered has reached every one of its receivers. No receiver can
    then see another receiver's reaction to an event before handling that
    event itself, whatever order the receivers are called in.
    """

    def receivers_for(self, sender):
        # Connection order, unlike object hashes, is stable across processes.
        connected = {
            make_id(receiver): receiver
            for receiver in super().receivers_for(sender)
        }
        for identity in list(self.receivers):
            if identity in connected:
                yield connected[identity]

    def send(self, sender: Any | None = None, /, **kwargs: Any) -> list:
        pending = getattr(_delivery, "pending", None)
        if pending is not None:
            pending.append((self, sender, kwargs))
            return []

        _delivery.pending = deque([(self, sender, kwargs)])
        try:
            self._drain()
        finally:
            _delivery.pending = None
        return []

    @staticmethod
    def _drain() -> None:
        pending = _delivery.pending
        while pending:
            named_signal, sender, kwargs = pending.popleft()
            named_signal._deliver(sender, **kwargs)

    def _deliver(self, sender: Any | None, **kwargs: Any) -> None:
        NamedSignal.send(self, sender, **kwargs)


# Global variable for managing signals in the app
signal_namespace: dict[str, Signal] = {}


def signal(name: str) -> Signal:
    """
    The signal of this name, created on first use. Repeated calls with the
    same name return the same signal.
    """
    if name not in signal_namespace:
        signal_namespace[name] = Signal(name)
    return signal_namespace[name]


def subscribe(signal_name: str, strict: bool = False):
    """
    Link a signal to a callback function as its receiver. The linked signal
    will connect to this callback on invoking ISignalSubscriber.connect.

    Args:
        signal_name: Name of the signal to link.
        strict: When enabled, the signal has to be defined ahead.
    """
    if not isinstance(signal_name, str):
        raise RuntimeError(
            f"Expects input <signal_name> to be a string, "
            f"but got {type(signal_name)}"
        )

    if strict and signal_name not in signal_namespace.keys():
        raise RuntimeError(
            f"Unknown signal name: {signal_name}, "
            f"possible values: {list(signal_namespace.keys())}"
        )

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Duck-typed to avoid importing Heartbeater into this generic
            # event module.
            start_heartbeating = getattr(self, "start_heartbeating", None)
            if start_heartbeating:
                start_heartbeating()
            return func(self, *args, **kwargs)

        wrapper.__signal__ = signal(signal_name)
        return wrapper

    return decorator
