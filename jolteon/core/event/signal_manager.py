import logging

from blinker import ANY

from jolteon.core.event.signal import signal_namespace
from jolteon.core.event.signal_subscriber import SignalSubscriber


class SignalManager:
    """
    A central manager for managing all signals in the application.
    """

    def connect_all(self) -> None:
        """
        Connect signal receivers to signals for every signal subscriber
        in the app

        Args:
            app:

        Returns:

        """
        for attr_name in dir(self):
            signal_subscriber = getattr(self, attr_name)
            if isinstance(signal_subscriber, SignalSubscriber):
                signal_subscriber.connect()

    @staticmethod
    def disconnect_all() -> None:
        """
        Disconnect all signals from its receivers

        Returns:
            None
        """
        for named_signal in signal_namespace.values():
            receivers = named_signal.receivers_for(ANY)
            if receivers:
                logging.info(
                    f"Disconnecting signal {named_signal.name} "
                    f"from its {len(named_signal.receivers.values())} "
                    f"receivers"
                )
            for receiver in receivers:
                named_signal.disconnect(receiver=receiver)
