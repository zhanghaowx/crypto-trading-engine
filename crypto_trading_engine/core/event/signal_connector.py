import atexit
import logging
import sqlite3
from enum import Enum

import pandas as pd
from blinker import NamedSignal, Signal, signal


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

    def close(self):
        """
        Disconnect all signals and dump recorded signal data to sqlite database

        Returns:
            None
        """
        for sender in self._signals:
            sender.disconnect(self._handle_signal)

        conn = sqlite3.connect(self._database_name)
        for name, df in self._events.items():
            logging.info(f"Saving DataFrame {name} with shape {df.shape}...")
            df.to_sql(name=name, con=conn, if_exists="replace")
        conn.close()

        self._events.clear()
        self._signals.clear()

    def _handle_signal(self, sender: NamedSignal, **kwargs):
        name = sender.name

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

            if not hasattr(payload, "PRIMARY_KEY"):
                logging.error(
                    f"Fail to persist signal {name}: "
                    f"DataFrame index column not specified!"
                )
                return

        for data in kwargs.values():
            row_data = vars(data)

            # Convert Enum values to its string representation
            for key, value in row_data.items():
                if isinstance(value, Enum):
                    row_data[key] = value.name

            df = pd.DataFrame([row_data])
            if name not in self._events:
                self._events[name] = df
            else:
                self._events[name] = pd.concat(
                    [self._events[name], df]
                ).drop_duplicates(subset=data.PRIMARY_KEY, keep="last")
