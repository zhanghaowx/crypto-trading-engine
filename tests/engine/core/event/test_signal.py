import unittest
from unittest.mock import patch

from blinker import NamedSignal

from jolteon.engine.core.event.signal import (
    Signal,
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
        # Patched on Signal itself: Signal.receivers_for puts whatever the
        # blinker base yields back into connection order, so perturbing
        # the base would leave the delivery order untouched.
        receivers_for = Signal.receivers_for

        for arrange in (list, lambda receivers: list(reversed(receivers))):
            self.calls.clear()
            with patch.object(
                Signal,
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


class TestConnectionOrderDelivery(unittest.TestCase):
    """
    blinker yields receivers in the iteration order of a set of object
    ids, which differs from one process to the next. Two replays compared
    across processes need the order the receivers were connected in.
    """

    def setUp(self):
        self.calls = list[str]()
        self.tick = signal("connection_order_tick")

    def first(self, _):
        self.calls.append("first")

    def second(self, _):
        self.calls.append("second")

    def test_receivers_run_in_connection_order_whatever_blinker_yields(self):
        def third(_):
            self.calls.append("third")

        # Bound methods and a plain function: blinker identifies the two
        # kinds differently, and both have to be put back in order.
        for receiver in (self.first, self.second, third):
            self.tick.connect(receiver)
        yielded = NamedSignal.receivers_for
        yielded_order = list[str]()

        def yielded_backwards(named_signal, sender):
            # blinker's own order is arbitrary; sorting makes the
            # perturbation the same on every run.
            receivers = sorted(
                yielded(named_signal, sender),
                key=lambda receiver: receiver.__name__,
                reverse=True,
            )
            yielded_order.extend(receiver.__name__ for receiver in receivers)
            return iter(receivers)

        with patch.object(NamedSignal, "receivers_for", yielded_backwards):
            self.tick.send(self.tick)

        self.assertEqual(["third", "second", "first"], yielded_order)
        self.assertEqual(["first", "second", "third"], self.calls)

    def test_a_receiver_connected_for_another_sender_is_still_left_out(self):
        self.tick.connect(self.first, sender="another sender")
        self.tick.connect(self.second)

        self.tick.send(self.tick)

        self.assertEqual(["second"], self.calls)
