from collections.abc import Callable, Iterator

from blinker import NamedSignal


class SignalSubscriber:
    """
    Base class for signal subscribers
    """

    def connect(self) -> None:
        """
        Automatically connect signals to its receivers that are marked by
        @subscribe.
        """
        for signal, receiver in self._subscriptions():
            signal.connect(receiver)

    def disconnect(self) -> None:
        for signal, receiver in self._subscriptions():
            signal.disconnect(receiver)

    def _subscriptions(self) -> Iterator[tuple[NamedSignal, Callable]]:
        for attr_name in dir(self):
            receiver = getattr(self, attr_name)
            signal = getattr(receiver, "__signal__", None)
            if signal and callable(receiver):
                yield signal, receiver
