import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from enum import Enum
from unittest.mock import patch, MagicMock

import pandas as pd
import pytz

from jolteon.core.event.signal import signal
from jolteon.core.event.signal_recorder import (
    SignalRecorder,
)
from jolteon.core.time.time_manager import time_manager


class TestSignalRecorder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database_filepath = f"{tempfile.gettempdir()}/unittest.sqlite"
        self.signal_a = signal("signal_a")
        self.signal_b = signal("signal_b")
        self.signal_recorder = SignalRecorder(self.database_filepath)

        def receiver_a(sender, **kwargs):
            pass

        def receiver_b(sender, **kwargs):
            pass

        self.signal_a.connect(receiver_a)
        self.signal_b.connect(receiver_b)
        self.signal_recorder.start_recording()

    async def asyncTearDown(self) -> None:
        if self.signal_recorder:
            self.signal_recorder.stop_recording()
        os.remove(self.database_filepath)

    async def test_connect(self):
        """
        Tests the connect method of the SignalRecorder class.
        """
        self.assertTrue(self.signal_a.receivers)
        self.assertTrue(self.signal_b.receivers)

        # Send signals that cannot be converted to dict, should be skipped
        self.signal_a.send(self.signal_a, message="Signal A")
        self.assertNotIn("signal_a", self.signal_recorder._events)

        self.signal_b.send(self.signal_b, message="Signal B")
        self.assertNotIn("signal_b", self.signal_recorder._events)

        # Send signals that cannot be converted to dict, should be skipped
        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        self.assertIn("signal_a", self.signal_recorder._events)

        self.signal_b.send(self.signal_b, message={"payload": "Signal B"})
        self.assertIn("signal_b", self.signal_recorder._events)

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

        self.assertIn("signal_a", self.signal_recorder._events)
        self.assertIn("signal_b", self.signal_recorder._events)

        event_a = self.signal_recorder._events["signal_a"]
        event_b = self.signal_recorder._events["signal_b"]

        expected_event_a = [{"payload_id": 1, "some_enum": "A"}]
        expected_event_b = [{"payload_id": 2, "some_enum": "A"}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

        # Send the same signal again, should not create duplicate events

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        event_a1 = self.signal_recorder._events["signal_a"]
        event_b1 = self.signal_recorder._events["signal_b"]

        self.assertEqual(event_a1, expected_event_a)
        self.assertEqual(event_b1, expected_event_b)

        # Send different signals with extra args, should be skipped

        self.signal_a.send(self.signal_a, payload=payload_b, other_args=True)
        self.signal_b.send(self.signal_b, payload=payload_a, other_args=True)

        event_a2 = self.signal_recorder._events["signal_a"]
        event_b2 = self.signal_recorder._events["signal_b"]

        self.assertEqual(event_a2, expected_event_a)
        self.assertEqual(event_b2, expected_event_b)

        # Send signals that cannot be converted to dict, should be skipped

        self.signal_a.send(self.signal_a, payload="payload_a")
        self.signal_b.send(self.signal_b, payload="payload_b")

        event_a3 = self.signal_recorder._events["signal_a"]
        event_b3 = self.signal_recorder._events["signal_b"]

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

        self.signal_recorder.start_recording()

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_recorder._events)
        self.assertIn("signal_b", self.signal_recorder._events)
        self.assertEqual(1, len(self.signal_recorder._events["signal_a"]))
        self.assertEqual(1, len(self.signal_recorder._events["signal_b"]))

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertEqual(2, len(self.signal_recorder._events["signal_a"]))
        self.assertEqual(2, len(self.signal_recorder._events["signal_b"]))

    async def test_handle_payload_has_array(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.array = [payload_id, payload_id + 1]

        payload_a = Payload(10)
        payload_b = Payload(20)

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assertIn("signal_a", self.signal_recorder._events)
        self.assertIn("signal_b", self.signal_recorder._events)

        event_a = self.signal_recorder._events["signal_a"]
        event_b = self.signal_recorder._events["signal_b"]

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

        self.assertIn("signal_a", self.signal_recorder._events)
        self.assertIn("signal_b", self.signal_recorder._events)

        event_a = self.signal_recorder._events["signal_a"]
        event_b = self.signal_recorder._events["signal_b"]

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

        self.assertIn("signal_a", self.signal_recorder._events)
        self.assertIn("signal_b", self.signal_recorder._events)

        event_a = self.signal_recorder._events["signal_a"]
        event_b = self.signal_recorder._events["signal_b"]

        expected_event_a = [{"tup.0": 10, "tup.1": 11}]
        expected_event_b = [{"tup.0": 20, "tup.1": 21}]

        self.assertEqual(event_a, expected_event_a)
        self.assertEqual(event_b, expected_event_b)

    async def test_handle_payload_has_datetime(self):
        class Payload:
            def __init__(self, new_key, new_value):
                self.dict = {
                    "time": time_manager().now(),
                    new_key: new_value,
                }

        payload_a = Payload("C", "3")

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.assertIn("signal_a", self.signal_recorder._events)

        self.signal_recorder._save_data()
        self.assertNotIn("signal_a", self.signal_recorder._events)

        # Force a schema change so to trigger a table merge
        payload_aa = Payload("D", "4")

        self.signal_a.send(self.signal_a, payload=payload_aa)
        self.assertIn("signal_a", self.signal_recorder._events)

        self.signal_recorder._save_data()
        self.assertNotIn("signal_a", self.signal_recorder._events)

    async def test_handle_payload_update_schema(self):
        class Payload:
            def __init__(self, new_key, new_value):
                self.dict = {
                    "A": "1",
                    "B": "2",
                    new_key: new_value,
                }

        payload_a = Payload("C", "3")

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.assertIn("signal_a", self.signal_recorder._events)

        self.signal_recorder._save_data()
        self.assertNotIn("signal_a", self.signal_recorder._events)

        payload_aa = Payload("D", "4")

        self.signal_a.send(self.signal_a, payload=payload_aa)
        self.assertIn("signal_a", self.signal_recorder._events)

        self.signal_recorder._save_data()
        self.assertNotIn("signal_a", self.signal_recorder._events)

        # Verify saved table
        conn = sqlite3.connect(database=self.database_filepath)
        df = pd.read_sql("SELECT * FROM signal_a", con=conn)
        conn.close()

        self.assertEqual(2, len(df))

    async def test_handle_payload_no_change_to_schema(self):
        class Payload:
            def __init__(self):
                self.dict = {
                    "A": "1",
                    "B": 3,
                    "C": True,
                    "D": datetime.now(tz=pytz.utc),
                }

        # Create an empty table
        conn = sqlite3.connect(database=self.database_filepath)
        conn.execute(
            """
        CREATE TABLE signal_a (
            A TEXT,
            B INTEGER,
            C INTEGER,
            D INTEGER
        );"""
        )

        payload_a = Payload()

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_recorder._save_data()

        # Verify saved table
        df = pd.read_sql("SELECT * FROM signal_a", con=conn)
        conn.close()

        self.assertEqual(1, len(df))

    async def test_handle_payload_is_none(self):
        self.signal_a.send(self.signal_a, payload=None)
        self.signal_b.send(self.signal_b, payload=None)

        self.assertNotIn("signal_a", self.signal_recorder._events)
        self.assertNotIn("signal_b", self.signal_recorder._events)

    @patch("pandas.DataFrame.to_sql")
    async def test_auto_save(self, mock_to_sql):
        mock_to_sql.return_value = MagicMock()

        self.signal_recorder.enable_auto_save(auto_save_interval=0.1)

        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        mock_to_sql.assert_not_called()

        self.assertIn("signal_a", self.signal_recorder._events)
        await asyncio.sleep(0.2)

        self.assertNotIn("signal_b", self.signal_recorder._events)
        mock_to_sql.assert_called_once()

        # Auto save will perform saving periodically

        mock_to_sql.reset_mock()

        self.signal_a.send(self.signal_a, message={"payload": "Signal AA"})
        mock_to_sql.assert_not_called()

        await asyncio.sleep(0.2)
        mock_to_sql.assert_called_once()

    @patch(
        "pandas.DataFrame.to_sql",
        side_effect=[Exception("SQL Error"), MagicMock()],
    )
    async def test_auto_save_exception(self, mock_to_sql):
        mock_to_sql.return_value = MagicMock()

        self.signal_recorder.enable_auto_save(auto_save_interval=0.1)

        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        mock_to_sql.assert_not_called()

        self.assertIn("signal_a", self.signal_recorder._events)
        await asyncio.sleep(0.2)

        self.assertNotIn("signal_b", self.signal_recorder._events)
        mock_to_sql.assert_called_once()

        # Auto save will perform saving periodically
        mock_to_sql.reset_mock()

        self.signal_a.send(self.signal_a, message={"payload": "Signal AA"})
        mock_to_sql.assert_not_called()

        await asyncio.sleep(0.2)
        mock_to_sql.assert_called_once()
