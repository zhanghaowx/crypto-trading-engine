import unittest
from unittest.mock import patch

from blinker import NamedSignal

from jolteon.engine.core.event.signal import (
    signal,
    signal_namespace,
    subscribe,
)


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
        signal("valid_signal")
        self.assertIn("valid_signal", signal_namespace.keys())

        # Test subscribing with valid input
        @subscribe("valid_signal")
        def callback():
            pass


class TestRunToCompletionDelivery(unittest.TestCase):
    def setUp(self):
        self.calls = list[str]()
        self.tick = signal("run_to_completion_tick")
        self.reaction = signal("run_to_completion_reaction")

    def reacting_receiver(self, _):
        self.calls.append("reacting receiver saw tick")
        self.reaction.send(self.reaction)

    def observing_receiver(self, _):
        self.calls.append("observing receiver saw tick")

    def on_reaction(self, _):
        self.calls.append("reaction delivered")

    def test_a_reaction_waits_until_every_receiver_has_the_event(self):
        self.tick.connect(self.reacting_receiver)
        self.tick.connect(self.observing_receiver)
        self.reaction.connect(self.on_reaction)
        receivers_for = NamedSignal.receivers_for

        for arrange in (list, lambda receivers: list(reversed(receivers))):
            self.calls.clear()
            with patch.object(
                NamedSignal,
                "receivers_for",
                lambda named_signal, sender: iter(
                    arrange(list(receivers_for(named_signal, sender)))
                ),
            ):
                self.tick.send(self.tick)

            self.assertEqual("reaction delivered", self.calls[-1])
            self.assertEqual(3, len(self.calls))

    def test_a_cycle_of_reactions_is_delivered_in_sequence(self):
        ping, pong = signal("cycle_ping"), signal("cycle_pong")
        depth = [0]
        max_depth = [0]

        def on_ping(_, count: int):
            depth[0] += 1
            max_depth[0] = max(max_depth[0], depth[0])
            self.calls.append(f"ping {count}")
            if count < 3:
                pong.send(pong, count=count + 1)
            depth[0] -= 1

        def on_pong(_, count: int):
            self.calls.append(f"pong {count}")
            ping.send(ping, count=count + 1)

        ping.connect(on_ping)
        pong.connect(on_pong)

        ping.send(ping, count=0)

        self.assertEqual(
            ["ping 0", "pong 1", "ping 2", "pong 3", "ping 4"], self.calls
        )
        self.assertEqual(1, max_depth[0])

    def test_a_failing_receiver_does_not_hold_back_later_events(self):
        def failing_receiver(_):
            self.reaction.send(self.reaction)
            raise RuntimeError("receiver failed")

        self.tick.connect(failing_receiver)
        self.reaction.connect(self.on_reaction)
        with self.assertRaises(RuntimeError):
            self.tick.send(self.tick)
        self.tick.disconnect(failing_receiver)
        self.calls.clear()

        self.reaction.send(self.reaction)

        self.assertEqual(["reaction delivered"], self.calls)
