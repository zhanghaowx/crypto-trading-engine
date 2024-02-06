import unittest

from jolteon.core.event.signal import subscribe, signal_namespace, signal


class TestSubscribeFunction(unittest.TestCase):
    def test_subscribe_invalid_input(self):
        # Test subscribing with invalid input
        with self.assertRaises(RuntimeError):

            @subscribe(123)
            def callback():
                pass

    def test_subscribe_unknown_signal(self):
        signal_name = "unknown_signal1"
        self.assertNotIn(signal_name, signal_namespace.keys())

        # Test subscribing to an unknown signal without strict mode
        @subscribe(signal_name)
        def callback():
            pass

    def test_subscribe_unknown_signal_strict(self):
        signal_name = "unknown_signal2"
        self.assertNotIn(signal_name, signal_namespace.keys())

        # Test subscribing to an unknown signal with strict mode
        with self.assertRaises(RuntimeError):

            @subscribe(signal_name, strict=True)
            def callback():
                pass

    def test_subscribe_valid_input(self):
        new_signal = signal("valid_signal")
        self.assertIn("valid_signal", signal_namespace.keys())

        # Test subscribing with valid input
        @subscribe("valid_signal")
        def callback():
            pass
