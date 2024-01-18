import asyncio
import atexit
import logging
import sqlite3
from enum import Enum
from typing import Any

import pandas as pd
from blinker import NamedSignal, Signal, signal
from pandas import json_normalize


class SignalConnector:
    """
    Help connect a signal to its subscribes and save a copy of every in SQLite
    database
    """

    def __init__(self, database_name="crypto.sqlite3"):
        self._database_name = database_name
        self._events = dict[str, pd.DataFrame]()
        self._signals = list[signal]()
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
        sender.connect(receiver=self._handle_signal)
        self._signals.append(sender)

    async def persist(self, interval_in_seconds=60):
        while True:
            self._save_data()
            await asyncio.sleep(interval_in_seconds)

    def close(self):
        """
        Disconnect all signals and dump recorded signal data to sqlite database

        Returns:
            None
        """
        self._save_data()
        self._clear_signals()

    def _save_data(self) -> None:
        """
        Dump all data into a SQLite database

        Returns:
            None
        """
        conn = sqlite3.connect(self._database_name)
        for name, df in self._events.items():
            logging.info(f"Saving DataFrame {name} with shape {df.shape}...")
            try:
                df.to_sql(name=name, con=conn, if_exists="append")
            except Exception as e:
                raise Exception(f"Cannot save DataFrame {name}: {e}")
        conn.close()

        self._events.clear()

    def _clear_signals(self):
        for sender in self._signals:
            sender.disconnect(self._handle_signal)
        self._signals.clear()

    def _handle_signal(self, sender: NamedSignal | str, **kwargs):
        if hasattr(sender, "name"):
            name = sender.name
        else:
            name = sender

        if len(kwargs.values()) != 1:
            logging.error(
                f"Fail to persist signal {name}: "
                f"{len(kwargs.values())} payloads found, expecting one!"
            )
            return

        for payload in kwargs.values():
            if not hasattr(payload, "__dict__"):
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

    @staticmethod
    def _to_dict(obj: Any):
        if obj is None:
            return None
        if isinstance(obj, Enum):
            return obj
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
