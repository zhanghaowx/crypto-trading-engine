import asyncio
import atexit
import logging
import sqlite3
import threading
from copy import copy
from datetime import datetime
from enum import Enum
from typing import Any

import flatdict
import pandas as pd
from blinker import NamedSignal

from jolteon.core.event.signal import signal_namespace
from jolteon.core.time.time_manager import time_manager


class SignalRecorder:
    """
    Help connect a signal to its subscribes and save a copy of every in SQLite
    database
    """

    def __init__(self, database_name="/tmp/jolteon.sqlite"):
        self._database_name = database_name
        self._events = dict[str, list]()
        self._events_lock = threading.Lock()
        self._auto_save_interval = 0
        self._auto_save_task = None

        atexit.register(self.stop_recording)

    def __del__(self):
        if self._auto_save_task is not None:
            self._auto_save_task.cancel()

    def enable_auto_save(self, auto_save_interval: float = 30):
        self._auto_save_task = asyncio.create_task(
            self._auto_save_data(auto_save_interval)
        )

    def start_recording(self):
        """
        Connect all signals and save a copy of each signal payload into a
        database. The payload may have a PRIMARY_KEY attribute. If the
        PRIMARY_KEY is set, duplicate rows will be removed from the DataFrame
        based on values in PRIMARY_KEY column. The sender shall invoke the
        `send` method with exactly one positional argument which is the sender,
        and exactly one keyword argument which is the payload.

        Returns:
            None
        """
        for name, signal in signal_namespace.items():
            logging.debug(f"Connecting to signal {name} for recording")
            signal.connect(receiver=self._handle_signal)

    def stop_recording(self):
        """
        Disconnect all signals and dump recorded signal data to sqlite database

        Returns:
            None
        """
        for name, signal in signal_namespace.items():
            logging.debug(f"Disconnecting from signal {name} for recording")
            signal.disconnect(receiver=self._handle_signal)
        self._save_data()

    async def _auto_save_data(self, auto_save_interval):
        while True:
            await asyncio.sleep(auto_save_interval)
            self._save_data()

    def _save_data(self) -> None:
        """
        Dump all data into a SQLite database

        Returns:
            None
        """
        conn = sqlite3.connect(self._database_name)
        with self._events_lock:
            events = copy(self._events)
        for name, payload_list in events.items():
            df = pd.DataFrame(payload_list)

            logging.debug(
                f"Saving DataFrame {name} with shape {df.shape} "
                f"to {self._database_name}..."
            )

            try:
                df.to_sql(name=name, con=conn, if_exists="append", index=False)
            except sqlite3.OperationalError as e:
                logging.warning(
                    f"Fail to save DataFrame {name} "
                    f"with shape {df.shape}: {e}. "
                    f"Try again to replace the whole table."
                )
                # In case more columns in df than what's already stored in DB,
                # do an update.
                existing_df = pd.read_sql(f"SELECT * FROM {name}", con=conn)
                if len(existing_df) > 0:
                    combined_df = pd.concat(
                        [existing_df, df], ignore_index=True, sort=False
                    )
                else:
                    combined_df = df

                try:
                    logging.info(
                        f"Re-saving DataFrame {name} with shape "
                        f"{combined_df.shape} to {self._database_name}..."
                    )
                    combined_df.to_sql(
                        name=name, con=conn, if_exists="replace", index=False
                    )
                except sqlite3.OperationalError as another_e:
                    logging.error(
                        f"Cannot save DataFrame {name}: "
                        f"'{another_e}', already retried after: '{e}'"
                    )

            except Exception as e:
                logging.error(f"Cannot save DataFrame {name}: '{e}'")

        # Clear all saved data
        with self._events_lock:
            self._events.clear()
        conn.close()

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

            with self._events_lock:
                if name not in self._events:
                    self._events[name] = [row_data]
                else:
                    payload_list = self._events[name]
                    if (
                        hasattr(data, "PRIMARY_KEY")
                        and len(payload_list) > 0
                        and payload_list[-1][data.PRIMARY_KEY]
                        == row_data[data.PRIMARY_KEY]
                    ):
                        # If PRIMARY_KEY is set, remove duplicates based on
                        # PRIMARY_KEY.
                        # However, for performance reasons, only the last
                        # element is checked.
                        # We don't have any other use case than the Candlestick
                        # event. Hence, we will treat it as a special case.
                        payload_list[-1] = row_data
                    else:
                        payload_list.append(row_data)

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
