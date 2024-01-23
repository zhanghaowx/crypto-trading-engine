import atexit
import logging
import sqlite3
from datetime import timedelta
from enum import Enum
from typing import Any

import pandas as pd
from blinker import NamedSignal, Signal
from pandas import json_normalize

from jolteon.core.time.time_manager import time_manager


class SignalConnector:
    """
    Help connect a signal to its subscribes and save a copy of every in SQLite
    database
    """

    def __init__(
        self, database_name="/tmp/jolteon.sqlite", auto_save_interval: int = 30
    ):
        self._database_name = database_name
        self._events = dict[str, pd.DataFrame]()
        self._signals = list[Signal]()
        self._receivers = list[object]()
        self._auto_save_interval = auto_save_interval
        self._auto_save_time = time_manager().now() + timedelta(
            seconds=auto_save_interval
        )
        atexit.register(self.close)

    def connect(self, sender: Signal, receiver=None):
        """
        Connects a signal sender to receiver, as well as making a copy of each
        signal payload and store in a DataFrame. In order to save the data, the
        payload must have a PRIMARY_KEY attribute. The PRIMARY_KEY is used to
        remove duplicate rows from the DataFrame. Additionally, the sender
        shall invoke the `send` method with exactly one positional
        argument which is the sender, and exactly one keyword
        argument which is the payload.

        Args:
            sender: Sender of the signal
            receiver: Receiver of the signal

        Returns:
            None
        """
        if receiver is not None:
            sender.connect(receiver=receiver)
            self._receivers.append(receiver)

        sender.connect(receiver=self._handle_signal)
        self._signals.append(sender)
        self._receivers.append(self._handle_signal)

    def close(self):
        """
        Disconnect all signals and dump recorded signal data to sqlite database

        Returns:
            None
        """
        self._clear_signals()
        self._save_data()

    def _save_data(self) -> None:
        """
        Dump all data into a SQLite database

        Returns:
            None
        """
        conn = sqlite3.connect(self._database_name)
        for name, df in self._events.items():
            logging.info(
                f"Saving DataFrame {name} with shape {df.shape} "
                f"to {self._database_name}..."
            )
            try:
                df.to_sql(name=name, con=conn, if_exists="replace")
            except Exception as e:
                raise Exception(f"Cannot save DataFrame {name}: {e}")
        conn.close()

    def _auto_save_data(self):
        if time_manager().now() > self._auto_save_time:
            self._auto_save_time = time_manager().now() + timedelta(
                seconds=self._auto_save_interval
            )
            self._save_data()

    def _clear_signals(self):
        for named_signal in self._signals:
            if self._receivers:
                logging.info(
                    f"Disconnecting signal {named_signal.name} "
                    f"from its {len(named_signal.receivers.values())} "
                    f"receivers"
                )
            for receiver in self._receivers:
                named_signal.disconnect(receiver=receiver)
        self._signals.clear()
        self._receivers.clear()

    def _handle_signal(self, sender: NamedSignal | str, **kwargs):
        assert isinstance(sender, NamedSignal)
        name = sender.name

        if len(kwargs.values()) != 1:
            logging.error(
                f"Fail to persist signal {name}: "
                f"{len(kwargs.values())} payloads found, expecting one!"
            )
            return

        for payload in kwargs.values():
            if not hasattr(payload, "__dict__") and not isinstance(
                payload, dict
            ):
                logging.error(
                    f"Fail to persist signal {name}: "
                    f"Cannot convert {type(payload)} to dict!"
                )
                return

        for data in kwargs.values():
            row_data = self._flatten_dict(self._to_dict(data))

            # Convert Enum values to its string representation
            for key, value in row_data.items():
                if isinstance(value, Enum):
                    row_data[key] = value.name

            df = pd.DataFrame([row_data])
            if name not in self._events:
                self._events[name] = df
            else:
                self._events[name] = pd.concat([self._events[name], df])
                if hasattr(data, "PRIMARY_KEY"):
                    self._events[name] = self._events[name].drop_duplicates(
                        subset=data.PRIMARY_KEY, keep="last"
                    )
                else:
                    self._events[name].reset_index()

        self._auto_save_data()

    @staticmethod
    def _to_dict(obj: Any):
        if obj is None:
            return None
        if isinstance(obj, Enum):
            return obj.value
        elif hasattr(obj, "__dict__") and obj.__dict__:
            return dict(
                [
                    (k, SignalConnector._to_dict(v))
                    for (k, v) in obj.__dict__.items()
                ]
            )
        elif isinstance(obj, (dict,)):
            return dict(
                [(k, SignalConnector._to_dict(v)) for (k, v) in obj.items()]
            )
        elif isinstance(obj, (list,)):
            return dict(
                {i: SignalConnector._to_dict(v) for i, v in enumerate(obj)}
            )
        elif isinstance(obj, (tuple,)):
            return dict(
                {i: SignalConnector._to_dict(v) for i, v in enumerate(obj)}
            )
        else:
            return obj

    @staticmethod
    def _flatten_dict(d: dict, sep: str = ".") -> dict:
        [flat_dict] = json_normalize(d, sep=sep).to_dict(orient="records")
        return flat_dict
