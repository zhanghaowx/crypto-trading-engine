import atexit
import logging
from datetime import datetime
from enum import Enum
from typing import Any

import flatdict
from blinker import NamedSignal

from jolteon.engine.core.event.signal import signal_namespace
from jolteon.engine.core.session.engine_run import engine_run_id
from jolteon.engine.core.session.trading_session import (
    trading_session_id,
    trading_session_id_at,
)
from jolteon.engine.core.sqlite_writer import SQLiteWriter
from jolteon.engine.core.time.time_manager import time_manager


class SignalRecorder:
    """
    Help connect a signal to its subscribers and save a copy of every
    payload in a SQLite database.

    Recording sits directly in the path of the market data thread, so the
    only work done there is flattening the payload and handing it to
    `SQLiteWriter`, which does the SQL on a thread of its own.

    Every row is stamped with the engine run that produced it and the
    trading session it belongs to, so a recording spanning several days
    and several restarts can be read back a session at a time without
    anything having to guess where one ended and the next began.
    """

    def __init__(self, database_name: str, run_id: str | None = None):
        self._database_name = database_name
        self._run_id = run_id or engine_run_id(time_manager().now())
        self._writer = SQLiteWriter(database_name)

        atexit.register(self._stop_quietly)

    def start_recording(self):
        """
        Connect all signals and save a copy of each signal payload into a
        database. The payload may have a PRIMARY_KEY attribute. If the
        PRIMARY_KEY is set, a later payload carrying a key already recorded
        updates that row instead of adding a duplicate. A payload that sets
        RECORDED to False is dispatched to its subscribers but never
        persisted, for payloads too wide to flatten into a row. The sender
        shall
        invoke the `send` method with exactly one positional argument which
        is the sender, and exactly one keyword argument which is the
        payload.

        Returns:
            None
        """
        for name, signal in signal_namespace.items():
            logging.debug(f"Connecting to signal {name} for recording")
            signal.connect(receiver=self._handle_signal)

    def stop_recording(self):
        """
        Disconnect all signals and wait for recorded data to reach the
        database.

        Returns:
            None
        """
        for name, signal in signal_namespace.items():
            logging.debug(f"Disconnecting from signal {name} for recording")
            signal.disconnect(receiver=self._handle_signal)
        self.flush()

    def flush(self):
        """
        Block until every signal recorded so far has reached the database.

        Recording is continuous, so this is only needed when a caller has to
        read back what it just recorded.

        Returns:
            None
        """
        self._writer.flush()

    def close(self):
        """Stop recording and shut the writer thread down."""
        self.stop_recording()
        self._writer.close()

    def _stop_quietly(self):
        """
        Stop recording at interpreter exit, where a failed write would only
        surface as a traceback from an atexit callback. SQLiteWriter reports
        it on stderr as it shuts down.
        """
        try:
            self.stop_recording()
        except Exception:
            pass

    def _handle_signal(self, sender: NamedSignal | str, **kwargs):
        assert isinstance(sender, NamedSignal)
        name = sender.name

        logging.debug("Received signal %s from %s", kwargs, name)

        if len(kwargs.values()) != 1:
            logging.error(
                f"Fail to persist signal {name}: "
                f"{len(kwargs.values())} payloads found, expecting one!",
                exc_info=True,
            )
            return

        for payload in kwargs.values():
            if not getattr(payload, "RECORDED", True):
                return

            if not hasattr(payload, "__dict__") and not isinstance(
                payload, dict
            ):
                logging.error(
                    f"Fail to persist signal {name}: "
                    f"Cannot convert {type(payload)} to dict!",
                    exc_info=True,
                )
                return

        for data in kwargs.values():
            row_data = dict(
                flatdict.FlatDict(self._to_dict(data), delimiter=".")
            )

            # Add timestamp column with record time to assist plotting data
            # as time series
            if "timestamp" not in row_data:
                row_data["timestamp"] = time_manager().now().timestamp()

            row_data["run_id"] = self._run_id
            if row_data.get("session_id") is None:
                row_data["session_id"] = self._session_of(row_data)

            primary_key = getattr(data, "PRIMARY_KEY", None)
            self._writer.put(name, row_data, primary_key)

    @staticmethod
    def _session_of(row_data: dict) -> str:
        """
        Returns: Which trading session the row belongs to.

        A payload knowing when its event really happened - a fill
        rewritten for half a minute as its markouts resolve - is taken at
        its word, since the recorder's own clock would put it in the next
        session. A timestamp that is not a moment leaves only that clock.
        """
        moment = row_data.get("timestamp")
        if isinstance(moment, (int, float)) and not isinstance(moment, bool):
            return trading_session_id_at(moment)
        return trading_session_id(time_manager().now())

    @staticmethod
    def _to_dict(obj: Any):
        if obj is None:
            return None
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, datetime):
            return obj.timestamp()
        elif hasattr(obj, "__dict__") and obj.__dict__:
            return dict(
                [
                    (k, SignalRecorder._to_dict(v))
                    for (k, v) in obj.__dict__.items()
                ]
            )
        elif isinstance(obj, (dict,)):
            return dict(
                [(k, SignalRecorder._to_dict(v)) for (k, v) in obj.items()]
            )
        elif isinstance(obj, (list,)):
            return dict(
                {str(i): SignalRecorder._to_dict(v) for i, v in enumerate(obj)}
            )
        elif isinstance(obj, (tuple,)):
            return dict(
                {str(i): SignalRecorder._to_dict(v) for i, v in enumerate(obj)}
            )
        else:
            return obj
