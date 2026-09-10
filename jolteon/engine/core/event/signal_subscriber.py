class SignalSubscriber:
    """
    Base class for signal subscribers
    """

    def connect(self) -> None:
        """
        Automatically connect signals to its receivers that are marked by
        @subscribe.
        """
        for attr_name in dir(self):
            receiver = getattr(self, attr_name)
            signal = getattr(receiver, "__signal__", None)
            if signal and callable(receiver):
                signal.connect(receiver)
