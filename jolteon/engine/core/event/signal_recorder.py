import atexit
import logging
from datetime import datetime
from enum import Enum
from typing import Any

import flatdict
from blinker import NamedSignal

from jolteon.engine.core.engine_run import engine_run_id
from jolteon.engine.core.event.signal import signal_namespace
from jolteon.engine.core.sqlite_writer import SQLiteWriter
from jolteon.engine.core.time.time_manager import time_manager


class SignalRecorder:
    """
    Help connect a signal to its subscribers and save a copy of every
    payload in a SQLite database.

    Recording sits directly in the path of the market data thread, so the
    only work done there is flattening the payload and handing it to
    `SQLiteWriter`, which does the SQL on a thread of its own.

    Every row is stamped with the engine run that produced it. A
    recorder made without one mints its own, so rows recorded outside an
    engine still say which process wrote them.
    """

    def __init__(self, database_name: str, run_id: str | None = None):
        self._database_name = database_name
        self._run_id = run_id or engine_run_id(time_manager().now())
        self._writer = SQLiteWriter(database_name)
        self._indexed = set[str]()

        atexit.register(self._stop_quietly)

    def start_recording(self):
        """
        Connect all signals and save a copy of each signal payload into a
        database. The payload may have a PRIMARY_KEY attribute. If the
        PRIMARY_KEY is set, a later payload carrying a key already recorded
        updates that row instead of adding a duplicate. It may also have an
        INDEX attribute naming the columns its table is indexed on, which
        is created once the first such payload has been recorded. A payload
        that sets RECORDED to False is dispatched to its subscribers but
        never persisted, for payloads too wide to flatten into a row. The
        sender shall invoke the `send` method with exactly one positional
        argument which is the sender, and exactly one keyword argument
        which is the payload.

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

            # The EngineRun row carries its own; nothing else does.
            row_data.setdefault("run_id", self._run_id)

            primary_key = getattr(data, "PRIMARY_KEY", None)
            self._writer.put(name, row_data, primary_key)

            if name not in self._indexed:
                self._indexed.add(name)
                index = getattr(data, "INDEX", None)
                if index:
                    self._writer.index(name, index)

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
