import asyncio
import atexit
import logging
import sqlite3
from enum import Enum
from typing import Any

import flatdict
import pandas as pd
from blinker import NamedSignal, Signal


class SignalConnector:
    """
    Help connect a signal to its subscribes and save a copy of every in SQLite
    database
    """

    def __init__(self, database_name="/tmp/jolteon.sqlite"):
        self._database_name = database_name
        self._events = dict[str, list]()
        self._signals = list[Signal]()
        self._receivers = list[object]()
        self._auto_save_interval = 0
        self._auto_save_task = None
        atexit.register(self.close)

    def __del__(self):
        if self._auto_save_task is not None:
            self._auto_save_task.cancel()

    def enable_auto_save(self, auto_save_interval: float = 30):
        asyncio.create_task(self._auto_save_data(auto_save_interval))

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
        for name, payload_list in self._events.items():
            df = pd.DataFrame(payload_list)

            logging.info(
                f"Saving DataFrame {name} with shape {df.shape} "
                f"to {self._database_name}..."
            )

            try:
                df.to_sql(name=name, con=conn, if_exists="append", index=False)
            except Exception as e:
                logging.warning(
                    f"Fail to save DataFrame {name} "
                    f"with shape {df.shape}: {e}. "
                    f"Try again to replace the whole table."
                )
                # In case more columns in df than what's already stored in DB,
                # do an update.
                existing_df = pd.read_sql(f"SELECT * FROM {name}", con=conn)
                if len(existing_df) > 0:
                    combined_df = pd.concat([existing_df, df], axis=1)
                else:
                    combined_df = df

                try:
                    combined_df.to_sql(
                        name=name, con=conn, if_exists="replace", index=False
                    )
                except Exception as another_e:
                    raise Exception(
                        f"Cannot save DataFrame {name}: "
                        f"'{another_e}', already retried after: '{e}'"
                        f", combined_df = {combined_df.columns}"
                        f", existing_df = {existing_df.columns}"
                        f", df = {df.columns}"
                    )

        # Clear all saved data
        self._events.clear()
        conn.close()

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
            # It is much more expensive to invoke _flatten_dict
            row_data = dict(
                flatdict.FlatDict(self._to_dict(data), delimiter=".")
            )
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
                    # However, for performance reasons, only the last element
                    # is checked.
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
                {
                    str(i): SignalConnector._to_dict(v)
                    for i, v in enumerate(obj)
                }
            )
        elif isinstance(obj, (tuple,)):
            return dict(
                {
                    str(i): SignalConnector._to_dict(v)
                    for i, v in enumerate(obj)
                }
            )
        else:
            return obj
