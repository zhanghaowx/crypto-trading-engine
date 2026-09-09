import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from datetime import datetime

import pandas as pd
import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class IDataSource(ABC):
    TRADE_CACHE = dict[tuple, list[Trade]]()

    @abstractmethod
    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        raise NotImplementedError

    def cache_key(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> tuple:
        """
        Key under which a download is cached.

        Every data source shares one cache, so the source is part of the
        key: replaying a recording and downloading from the exchange can
        both be asked for the same symbol over the same time range.
        """
        return (type(self).__name__, symbol, start_time, end_time)


class DatabaseDataSource(IDataSource):
    """
    Download historical market trades from a SQLite database
    """

    def __init__(self, database_name: str):
        self._database_name = database_name
        self._table_name = Events().market_trade.name
        self._index_name = f"ix_{self._table_name}_transaction_time"
        self._index_checked = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database_name)
        conn.execute("PRAGMA busy_timeout=30000")
        if not self._index_checked:
            self._index_checked = True
            try:
                # Every query here is bounded by transaction_time. Without
                # an index each one scans and sorts the whole recording,
                # which grows for as long as the engine runs.
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{self._index_name}" '
                    f'ON "{self._table_name}" (transaction_time)'
                )
            except sqlite3.OperationalError:
                # Nothing recorded yet, or the file cannot be written to.
                # The queries still work, just without the index.
                pass
        return conn

    def _bound(self, aggregate: str) -> datetime:
        """The earliest or latest transaction time in the recording."""
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    f"SELECT {aggregate}(transaction_time) "
                    f'FROM "{self._table_name}"'
                ).fetchone()
        except sqlite3.OperationalError as e:
            # The replay database is chosen by the caller, so report a
            # recording without market trades rather than a bare SQL error.
            raise ValueError(
                f"No market trades recorded in {self._database_name}: {e}"
            ) from e

        if row is None or row[0] is None:
            raise ValueError(
                f"No market trades recorded in {self._database_name}"
            )
        return datetime.fromtimestamp(float(row[0]), tz=pytz.utc)

    def start_time(self) -> datetime:
        return self._bound("MIN")

    def end_time(self) -> datetime:
        return self._bound("MAX")

    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        key = self.cache_key(symbol, start_time, end_time)
        cached = self.TRADE_CACHE.get(key)
        if cached is not None:
            return cached

        # Filter in SQL rather than after loading: a recording holds a whole
        # session, and a replay usually wants a slice of it. Reading it all
        # back would build a Trade for every row only to discard most.
        with closing(self._connect()) as conn:
            df = pd.read_sql(
                f'SELECT * FROM "{self._table_name}" '
                f"WHERE transaction_time BETWEEN ? AND ? "
                f"ORDER BY transaction_time ASC",
                con=conn,
                params=(start_time.timestamp(), end_time.timestamp()),
            )
        market_trades = self.to_trades(df)

        self.TRADE_CACHE[key] = market_trades

        return market_trades

    @staticmethod
    def to_trades(df: pd.DataFrame) -> list[Trade]:
        """
        Converts a pandas dataframe to a list of trades
        Args:
            df:

        Returns:

        """
        market_trades = list[Trade]()
        for trade_dict in df.to_dict(orient="records"):
            market_trades.append(
                Trade(
                    trade_id=trade_dict["trade_id"],
                    client_order_id=trade_dict["client_order_id"],
                    symbol=trade_dict["symbol"],
                    maker_order_id=trade_dict["maker_order_id"],
                    taker_order_id=trade_dict["taker_order_id"],
                    side=MarketSide.parse(trade_dict["side"]),
                    price=float(trade_dict["price"]),
                    fee=float(trade_dict["fee"]),
                    quantity=float(trade_dict["quantity"]),
                    transaction_time=datetime.fromtimestamp(
                        float(trade_dict["transaction_time"]), tz=pytz.utc
                    ),
                )
            )
        return market_trades
