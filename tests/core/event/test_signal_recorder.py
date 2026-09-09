import os
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from enum import Enum

import pandas as pd
import pytz
from freezegun import freeze_time

from jolteon.core.event.signal import signal
from jolteon.core.event.signal_recorder import SignalRecorder
from jolteon.core.time.time_manager import time_manager


class TestSignalRecorder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )
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
            self.signal_recorder.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.database_filepath + suffix
            if os.path.exists(path):
                os.remove(path)

    def rows(self, table: str) -> pd.DataFrame:
        """Everything recorded into `table` so far, as recorded."""
        self.signal_recorder.flush()
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            try:
                return pd.read_sql(f'SELECT * FROM "{table}"', con=conn)
            except pd.errors.DatabaseError:
                return pd.DataFrame()

    def assert_recorded(self, table: str, expected: list[dict]):
        recorded = self.rows(table).to_dict(orient="records")
        self.assertEqual(expected, recorded)

    async def test_connect(self):
        """
        Tests the connect method of the SignalRecorder class.
        """
        self.assertTrue(self.signal_a.receivers)
        self.assertTrue(self.signal_b.receivers)

        # Send signals that cannot be converted to dict, should be skipped
        self.signal_a.send(self.signal_a, message="Signal A")
        self.signal_b.send(self.signal_b, message="Signal B")

        self.assertTrue(self.rows("signal_a").empty)
        self.assertTrue(self.rows("signal_b").empty)

        # Send signals that can be converted to dict, should be recorded
        self.signal_a.send(self.signal_a, message={"payload": "Signal A"})
        self.signal_b.send(self.signal_b, message={"payload": "Signal B"})

        self.assertEqual(1, len(self.rows("signal_a")))
        self.assertEqual(1, len(self.rows("signal_b")))

    @freeze_time("2024-01-01 00:00:30 UTC")
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

        expected_event_a = [
            {"payload_id": 1, "some_enum": "A", "timestamp": 1704067230.0}
        ]
        expected_event_b = [
            {"payload_id": 2, "some_enum": "A", "timestamp": 1704067230.0}
        ]

        self.assert_recorded("signal_a", expected_event_a)
        self.assert_recorded("signal_b", expected_event_b)

        # Send the same signal again, should update rather than duplicate

        self.signal_a.send(self.signal_a, payload=payload_a)
        self.signal_b.send(self.signal_b, payload=payload_b)

        self.assert_recorded("signal_a", expected_event_a)
        self.assert_recorded("signal_b", expected_event_b)

        # Send different signals with extra args, should be skipped

        self.signal_a.send(self.signal_a, payload=payload_b, other_args=True)
        self.signal_b.send(self.signal_b, payload=payload_a, other_args=True)

        self.assert_recorded("signal_a", expected_event_a)
        self.assert_recorded("signal_b", expected_event_b)

        # Send signals that cannot be converted to dict, should be skipped

        self.signal_a.send(self.signal_a, payload="payload_a")
        self.signal_b.send(self.signal_b, payload="payload_b")

        self.assert_recorded("signal_a", expected_event_a)
        self.assert_recorded("signal_b", expected_event_b)

    @freeze_time("2024-01-01 00:00:30 UTC")
    async def test_handle_payload_primary_key_keeps_latest_value(self):
        """
        A candlestick is re-sent as it fills in, under the same key. The
        stored row has to end up holding the newest values, not the first.
        """

        class Payload:
            PRIMARY_KEY = "payload_id"

            def __init__(self, payload_id: int, close: float):
                self.payload_id = payload_id
                self.close = close

        self.signal_a.send(self.signal_a, payload=Payload(1, 10.0))
        self.signal_a.send(self.signal_a, payload=Payload(1, 11.0))
        self.signal_a.send(self.signal_a, payload=Payload(2, 12.0))

        self.assert_recorded(
            "signal_a",
            [
                {"payload_id": 1, "close": 11.0, "timestamp": 1704067230.0},
                {"payload_id": 2, "close": 12.0, "timestamp": 1704067230.0},
            ],
        )

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

        self.assertEqual(1, len(self.rows("signal_a")))
        self.assertEqual(1, len(self.rows("signal_b")))

        signal_a.send(signal_a, payload=payload_a)
        signal_b.send(signal_b, payload=payload_b)

        self.assertEqual(2, len(self.rows("signal_a")))
        self.assertEqual(2, len(self.rows("signal_b")))

    @freeze_time("2024-01-01 00:00:30 UTC")
    async def test_handle_payload_has_array(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.array = [payload_id, payload_id + 1]

        self.signal_a.send(self.signal_a, payload=Payload(10))
        self.signal_b.send(self.signal_b, payload=Payload(20))

        self.assert_recorded(
            "signal_a",
            [{"array.0": 10, "array.1": 11, "timestamp": 1704067230.0}],
        )
        self.assert_recorded(
            "signal_b",
            [{"array.0": 20, "array.1": 21, "timestamp": 1704067230.0}],
        )

    @freeze_time("2024-01-01 00:00:30 UTC")
    async def test_handle_payload_nested_dict(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.dict = {
                    "a": payload_id,
                    "b": payload_id + 1,
                }

        self.signal_a.send(self.signal_a, payload=Payload(10))
        self.signal_b.send(self.signal_b, payload=Payload(20))

        self.assert_recorded(
            "signal_a",
            [{"dict.a": 10, "dict.b": 11, "timestamp": 1704067230.0}],
        )
        self.assert_recorded(
            "signal_b",
            [{"dict.a": 20, "dict.b": 21, "timestamp": 1704067230.0}],
        )

    @freeze_time("2024-01-01 00:00:30 UTC")
    async def test_handle_payload_nested_tuple(self):
        class Payload:
            def __init__(self, payload_id: int):
                self.tup = (payload_id, payload_id + 1)

        self.signal_a.send(self.signal_a, payload=Payload(10))
        self.signal_b.send(self.signal_b, payload=Payload(20))

        self.assert_recorded(
            "signal_a",
            [{"tup.0": 10, "tup.1": 11, "timestamp": 1704067230.0}],
        )
        self.assert_recorded(
            "signal_b",
            [{"tup.0": 20, "tup.1": 21, "timestamp": 1704067230.0}],
        )

    async def test_handle_payload_has_datetime(self):
        class Payload:
            def __init__(self, new_key, new_value):
                self.dict = {
                    "time": time_manager().now(),
                    new_key: new_value,
                }

        self.signal_a.send(self.signal_a, payload=Payload("C", "3"))

        # Force a schema change so a new column has to be added
        self.signal_a.send(self.signal_a, payload=Payload("D", "4"))

        recorded = self.rows("signal_a")
        self.assertEqual(2, len(recorded))
        self.assertIn("dict.C", recorded.columns)
        self.assertIn("dict.D", recorded.columns)
        # A datetime is stored as a POSIX timestamp, not an object
        self.assertTrue(
            all(isinstance(value, float) for value in recorded["dict.time"])
        )

    async def test_handle_payload_has_timestamp(self):
        class Payload:
            def __init__(self):
                self.timestamp = "Hello"

        self.signal_a.send(self.signal_a, payload=Payload())

        self.assert_recorded("signal_a", [{"timestamp": "Hello"}])

    async def test_handle_payload_update_schema(self):
        """
        A payload that grows a field widens the table in place; rows already
        recorded stay put and simply carry NULL in the new column.
        """

        class Payload:
            def __init__(self, new_key, new_value):
                self.dict = {
                    "A": "1",
                    "B": "2",
                    new_key: new_value,
                }

        self.signal_a.send(self.signal_a, payload=Payload("C", "3"))
        self.assertEqual(1, len(self.rows("signal_a")))

        self.signal_a.send(self.signal_a, payload=Payload("D", "4"))

        recorded = self.rows("signal_a")
        self.assertEqual(2, len(recorded))
        self.assertEqual("3", recorded["dict.C"][0])
        self.assertTrue(pd.isna(recorded["dict.C"][1]))
        self.assertTrue(pd.isna(recorded["dict.D"][0]))
        self.assertEqual("4", recorded["dict.D"][1])

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
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(
                """
            CREATE TABLE signal_a (
                A TEXT,
                B INTEGER,
                C INTEGER,
                D INTEGER
            );"""
            )
            conn.commit()

        self.signal_a.send(self.signal_a, payload=Payload())

        recorded = self.rows("signal_a")
        self.assertEqual(1, len(recorded))
        # The pre-existing columns survive; the payload's own are added
        for column in ("A", "B", "C", "D", "dict.A", "dict.B"):
            self.assertIn(column, recorded.columns)

    async def test_handle_payload_is_none(self):
        self.signal_a.send(self.signal_a, payload=None)
        self.signal_b.send(self.signal_b, payload=None)

        self.assertTrue(self.rows("signal_a").empty)
        self.assertTrue(self.rows("signal_b").empty)

    async def test_record_from_different_threads(self):
        """
        Signals are sent from the market data thread as well as the engine's
        event loop, so nothing may be dropped when senders overlap.
        """
        num_threads = 50
        payloads = [{"payload": f"Signal {i}"} for i in range(num_threads)]

        def worker(payload):
            self.signal_a.send(self.signal_a, message=payload)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            list(executor.map(worker, payloads))

        recorded = self.rows("signal_a")
        self.assertEqual(num_threads, len(recorded))
        self.assertEqual(
            {p["payload"] for p in payloads},
            set(recorded["payload"]),
        )
