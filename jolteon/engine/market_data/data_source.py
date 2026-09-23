import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.events import Events
from jolteon.engine.market_data.core.order_book import (
    BookModel,
    RecordedBookUpdate,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.provenance import MarketDataProvenance


class IDataSource(ABC):
    TRADE_CACHE = dict[tuple, list[Trade]]()

    @abstractmethod
    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        raise NotImplementedError

    async def download_order_book_updates(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[RecordedBookUpdate]:
        """Return normalized book records when this source provides them."""
        return []

    def provenance(
        self, start_time: datetime, end_time: datetime
    ) -> MarketDataProvenance:
        """
        Returns: Where the data this source hands back came from.

        A source with nothing more to say than what it is answers with
        its own name, which still separates a replay off a recording from
        one off a venue's history.
        """
        return MarketDataProvenance(source=type(self).__name__)

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
        self._book_table_name = Events().order_book_update.name
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

    def provenance(
        self, start_time: datetime, end_time: datetime
    ) -> MarketDataProvenance:
        """
        Returns: Which file was replayed, which run recorded it, and how
        many market trades the interval holds.

        The run is only reported when the interval holds exactly one; a
        recording spanning several runs, or one written before rows
        carried a run at all, leaves it unanswered rather than picking
        one of them.
        """
        return MarketDataProvenance(
            source=str(Path(self._database_name).resolve()),
            source_run_id=self._single_run_id(start_time, end_time),
            trade_count=self._trade_count(start_time, end_time),
        )

    def _single_run_id(
        self, start_time: datetime, end_time: datetime
    ) -> str | None:
        rows = self._query(
            f'SELECT DISTINCT run_id FROM "{self._table_name}" '
            "WHERE transaction_time BETWEEN ? AND ? LIMIT 2",
            (start_time.timestamp(), end_time.timestamp()),
        )
        if rows is None or len(rows) != 1 or rows[0][0] is None:
            return None
        return str(rows[0][0])

    def _trade_count(
        self, start_time: datetime, end_time: datetime
    ) -> int | None:
        rows = self._query(
            f'SELECT COUNT(*) FROM "{self._table_name}" '
            "WHERE transaction_time BETWEEN ? AND ?",
            (start_time.timestamp(), end_time.timestamp()),
        )
        return None if rows is None else int(rows[0][0])

    def _query(self, statement: str, parameters: tuple) -> list | None:
        """
        Returns: The rows the statement selects, and nothing at all when
        the recording has no such table or column.

        Provenance is recorded so a replay can be traced afterwards; a
        recording too old to answer must leave the question open rather
        than stop the replay.
        """
        try:
            with closing(self._connect()) as conn:
                return conn.execute(statement, parameters).fetchall()
        except sqlite3.OperationalError:
            return None

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

    async def download_order_book_updates(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[RecordedBookUpdate]:
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    f"SELECT symbol, model, version, sequence, bids, asks, "
                    "is_snapshot, exchange_time FROM "
                    f'"{self._book_table_name}" '
                    "WHERE symbol = ? AND exchange_time BETWEEN ? AND ? "
                    "ORDER BY exchange_time ASC, rowid ASC",
                    (symbol, start_time.timestamp(), end_time.timestamp()),
                ).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                return []
            raise

        return [
            RecordedBookUpdate(
                symbol=row[0],
                model=BookModel(row[1]),
                version=int(row[2]),
                sequence=int(row[3]),
                bids=row[4],
                asks=row[5],
                is_snapshot=bool(row[6]),
                exchange_time=datetime.fromtimestamp(
                    float(row[7]), tz=pytz.utc
                ),
            )
            for row in rows
        ]

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
                    exchange_trade_id=trade_dict["exchange_trade_id"],
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
