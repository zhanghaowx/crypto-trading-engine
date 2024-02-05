from blinker import Namespace

# Global variable for managing signals in the app
signal_namespace = Namespace()
signal = signal_namespace.signal


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
        func.__signal__ = signal(signal_name)
        return func

    return decorator
