import os
import unittest
from enum import Enum

import pandas as pd
from blinker import signal
from pandas.testing import assert_frame_equal

from crypto_trading_engine.core.event.signal_connector import (
    SignalConnector,
)


class TestSignalConnector(unittest.TestCase):
    def setUp(self) -> None:
        self.database_name = "unit_test.sqlite3"
        self.signal_connector = SignalConnector(self.database_name)

    def tearDown(self) -> None:
        self.signal_connector.close()
        if self.database_name in os.listdir():
            os.remove(self.database_name)

    # def tearDownClass(self) -> None:
    #     if self.database_name in os.listdir():
    #         os.remove(self.database_name)

    def test_connect(self):
        """
        Tests the connect method of the SignalConnector class.
        """
        signal_a = signal("signal_a")
        signal_b = signal("signal_b")

        def receiver_a(sender, **kwargs):
            pass

        def receiver_b(sender, **kwargs):
            pass

        self.signal_connector.connect(signal_a, receiver_a)
        self.signal_connector.connect(signal_b, receiver_b)

        self.assertTrue(signal_a.receivers)
        self.assertTrue(signal_b.receivers)

        signal_a.send(signal_a, message="Signal A")
        self.assertNotIn("signal_a", self.signal_connector.events)

        signal_b.send(signal_b, message="Signal B")
        self.assertNotIn("signal_b", self.signal_connector.events)

    def test_handle_signal(self):
        class SomeEnum(Enum):
            A = 1

        class Payload:
            PRIMARY_KEY = "payload_id"

            def __init__(self, payload_id: int):
                self.payload_id = payload_id
                self.some_enum = SomeEnum.A

        payload_a = Payload(1)
        payload_b = Payload(2)

        signal_a = signal("signal_a")
        signal_b = signal("signal_b")

        self.signal_connector.connect(signal_a)
        self.signal_connector.connect(signal_b)

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector.events)
        self.assertIn("signal_b", self.signal_connector.events)

        event_a = self.signal_connector.events["signal_a"]
        event_b = self.signal_connector.events["signal_b"]

        expected_event_a = pd.DataFrame(
            [vars(payload_a)], columns=list(vars(payload_a).keys())
        )
        expected_event_b = pd.DataFrame(
            [vars(payload_b)], columns=list(vars(payload_a).keys())
        )

        assert_frame_equal(event_a, expected_event_a)
        assert_frame_equal(event_b, expected_event_b)

        # Send the same signal again, should not create duplicate events

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        event_a1 = self.signal_connector.events["signal_a"]
        event_b1 = self.signal_connector.events["signal_b"]

        assert_frame_equal(event_a1, expected_event_a)
        assert_frame_equal(event_b1, expected_event_b)

        # Send different signals with extra args, should be skipped

        signal_a.send(signal_a, payload=payload_b, other_args=True)
        signal_b.send(signal_b, payload=payload_a, other_args=True)

        event_a2 = self.signal_connector.events["signal_a"]
        event_b2 = self.signal_connector.events["signal_b"]

        assert_frame_equal(event_a2, expected_event_a)
        assert_frame_equal(event_b2, expected_event_b)

        # Send signals that cannot be converted to dict, should be skipped

        signal_a.send(signal_a, payload="payload_a")
        signal_b.send(signal_b, payload="payload_b")

        event_a3 = self.signal_connector.events["signal_a"]
        event_b3 = self.signal_connector.events["signal_b"]

        assert_frame_equal(event_a3, expected_event_a)
        assert_frame_equal(event_b3, expected_event_b)
