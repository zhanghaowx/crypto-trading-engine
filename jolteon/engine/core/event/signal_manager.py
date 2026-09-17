from jolteon.engine.core.event.signal_subscriber import SignalSubscriber


class SignalManager:
    """
    A central manager for managing all signals in the application.
    """

    def connect_all(self) -> None:
        """
        Connect signal receivers to signals for every signal subscriber
        in the app
        """
        for subscriber in self._signal_subscribers():
            subscriber.connect()

    def disconnect_all(self) -> None:
        """
        Disconnect the subscribers this app connected, leaving receivers
        that belong to anything else connected.
        """
        for subscriber in self._signal_subscribers():
            subscriber.disconnect()

    def _signal_subscribers(self) -> list[SignalSubscriber]:
        return [
            attribute
            for attribute in (getattr(self, name) for name in dir(self))
            if isinstance(attribute, SignalSubscriber)
        ]
