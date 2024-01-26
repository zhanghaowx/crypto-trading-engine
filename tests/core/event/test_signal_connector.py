import asyncio
import os
import tempfile
import unittest
from enum import Enum
from unittest.mock import patch, MagicMock

from blinker import signal

from jolteon.core.event.signal_connector import (
    SignalConnector,
)


class TestSignalConnector(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database_filepath = f"{tempfile.gettempdir()}/unittest.sqlite"
        self.signal_connector = SignalConnector(self.database_filepath)
        self.signal_a = signal("signal_a")
        self.signal_b = signal("signal_b")

        def receiver_a(sender, **kwargs):
            pass

        def receiver_b(sender, **kwargs):
            pass

        self.signal_connector.connect(self.signal_a, receiver_a)
        self.signal_connector.connect(self.signal_b, receiver_b)

    async def asyncTearDown(self) -> None:
        self.signal_connector.close()
        os.remove(self.database_filepath)

    async def test_connect(self):
        """
        Tests the connect method of the SignalConnector class.
        """
        self.assertTrue(self.signal_a.receivers)
        self.assertTrue(self.signal_b.receivers)

        # Send signals that cannot be converted to dict, should be skipped
        self.signal_a.send(self.signal_a, message="Signal A")
        self.assertNotIn("signal_a", self.signal_connector._events)

        self.signal_b.send(self.signal_b, message="Signal B")
        self.assertNotIn("signal_b", self.signal_connector._events)

        # Send signals that cannot be converted to dict, should be skipped
        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        self.assertIn("signal_a", self.signal_connector._events)

        self.signal_b.send(self.signal_b, message={"payload": "Signal B"})
        self.assertIn("signal_b", self.signal_connector._events)

    async def test_handle_payload_has_primary_key(self):
        class SomeEnum(Enum):
            A = "A"

        class Payload:
            PRIMARY_KEY = "payload_id"

            def __init__(self, payload_id: int):
                self.payload_id = payload_id
                self.some_enum = SomeEnum.A

        payload_a = Payload(1)
        payload_b = Payload(2)

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector._events)
        self.assertIn("signal_b", self.signal_connector._events)

        event_a = self.signal_connector._events["signal_a"]
        event_b = self.signal_connector._events["signal_b"]

        expected_event_a = [{"payload_id": 1, "some_enum": "A"}]
        expected_event_b = [{"payload_id": 2, "some_enum": "A"}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

        # Send the same signal again, should not create duplicate events

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        event_a1 = self.signal_connector._events["signal_a"]
        event_b1 = self.signal_connector._events["signal_b"]

        self.assertEqual(event_a1, expected_event_a)
        self.assertEqual(event_b1, expected_event_b)

        # Send different signals with extra args, should be skipped

        self.signal_a.send(self.signal_a, payload=payload_b, other_args=True)
        self.signal_b.send(self.signal_b, payload=payload_a, other_args=True)

        event_a2 = self.signal_connector._events["signal_a"]
        event_b2 = self.signal_connector._events["signal_b"]

        self.assertEqual(event_a2, expected_event_a)
        self.assertEqual(event_b2, expected_event_b)

        # Send signals that cannot be converted to dict, should be skipped

        self.signal_a.send(self.signal_a, payload="payload_a")
        self.signal_b.send(self.signal_b, payload="payload_b")

        event_a3 = self.signal_connector._events["signal_a"]
        event_b3 = self.signal_connector._events["signal_b"]

        self.assertEqual(event_a3, expected_event_a)
        self.assertEqual(event_b3, expected_event_b)

    async def test_handle_signal_payload_has_no_primary_key(self):
        class SomeEnum(Enum):
            A = 1

        class Payload:
            def __init__(self, payload_id: int):
                self.payload_id = payload_id
                self.some_enum = SomeEnum.A

        payload_a = Payload(1)
        payload_b = Payload(1)

        signal_a = signal("signal_a")
        signal_b = signal("signal_b")

        self.signal_connector.connect(signal_a)
        self.signal_connector.connect(signal_b)

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector._events)
        self.assertIn("signal_b", self.signal_connector._events)
        self.assertEqual(1, len(self.signal_connector._events["signal_a"]))
        self.assertEqual(1, len(self.signal_connector._events["signal_b"]))

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertEqual(2, len(self.signal_connector._events["signal_a"]))
        self.assertEqual(2, len(self.signal_connector._events["signal_b"]))

    async def test_handle_payload_has_array(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.array = [payload_id, payload_id + 1]

        payload_a = Payload(10)
        payload_b = Payload(20)

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector._events)
        self.assertIn("signal_b", self.signal_connector._events)

        event_a = self.signal_connector._events["signal_a"]
        event_b = self.signal_connector._events["signal_b"]

        expected_event_a = [{"array.0": 10, "array.1": 11}]
        expected_event_b = [{"array.0": 20, "array.1": 21}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

    async def test_handle_payload_nested_dict(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.dict = {
                    "a": payload_id,
                    "b": payload_id + 1,
                }

        payload_a = Payload(10)
        payload_b = Payload(20)

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector._events)
        self.assertIn("signal_b", self.signal_connector._events)

        event_a = self.signal_connector._events["signal_a"]
        event_b = self.signal_connector._events["signal_b"]

        expected_event_a = [{"dict.a": 10, "dict.b": 11}]
        expected_event_b = [{"dict.a": 20, "dict.b": 21}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

    async def test_handle_payload_nested_tuple(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.tup = (payload_id, payload_id + 1)

        payload_a = Payload(10)
        payload_b = Payload(20)

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_connector._events)
        self.assertIn("signal_b", self.signal_connector._events)

        event_a = self.signal_connector._events["signal_a"]
        event_b = self.signal_connector._events["signal_b"]

        expected_event_a = [{"tup.0": 10, "tup.1": 11}]
        expected_event_b = [{"tup.0": 20, "tup.1": 21}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

    async def test_handle_payload_is_none(self):
        self.signal_a.send(self.signal_a, payload=None)
        self.signal_b.send(self.signal_b, payload=None)

        self.assertNotIn("signal_a", self.signal_connector._events)
        self.assertNotIn("signal_b", self.signal_connector._events)

    @patch("pandas.DataFrame.to_sql")
    async def test_auto_save(self, mock_to_sql):
        mock_to_sql.return_value = MagicMock()

        self.signal_connector.enable_auto_save(auto_save_interval=0.001)

        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        mock_to_sql.assert_not_called()

        await asyncio.sleep(0.002)

        mock_to_sql.assert_called_once()
