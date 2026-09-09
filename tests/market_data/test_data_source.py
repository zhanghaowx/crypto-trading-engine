import os
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.events import Events
from jolteon.market_data.data_source import DatabaseDataSource, IDataSource


class TestDatabaseDataSource(unittest.IsolatedAsyncioTestCase):
    TABLE = Events().market_trade.name

    async def asyncSetUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )
        # The cache lives on the base class and outlives one test
        IDataSource.TRADE_CACHE.clear()
        self.start = datetime(2022, 1, 1, 10, 0, 0, tzinfo=pytz.utc)
        self.data_source = DatabaseDataSource(self.database_filepath)

    async def asyncTearDown(self):
        IDataSource.TRADE_CACHE.clear()
        for suffix in ("", "-wal", "-shm"):
            path = self.database_filepath + suffix
            if os.path.exists(path):
                os.remove(path)

    def record(self, count: int, seconds_apart: float = 60.0):
        """Write `count` market trades, one every `seconds_apart`."""
        rows = [
            (
                i + 1,
                f"client{i}",
                "BTC/USD",
                f"maker{i}",
                f"taker{i}",
                "buy" if i % 2 == 0 else "sell",
                100.0 + i,
                0.0,
                1.0,
                (
                    self.start + timedelta(seconds=i * seconds_apart)
                ).timestamp(),
            )
            for i in range(count)
        ]
        with sqlite3.connect(self.database_filepath) as conn:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{self.TABLE}" ('
                "trade_id, client_order_id, symbol, maker_order_id, "
                "taker_order_id, side, price, fee, quantity, "
                "transaction_time)"
            )
            conn.executemany(
                f'INSERT INTO "{self.TABLE}" VALUES (?,?,?,?,?,?,?,?,?,?)',
                rows,
            )

    async def test_download_market_trades(self):
        self.record(3)

        trades = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start,
            end_time=self.start + timedelta(minutes=10),
        )

        self.assertEqual(3, len(trades))
        self.assertEqual([1, 2, 3], [t.trade_id for t in trades])
        self.assertEqual("BTC/USD", trades[0].symbol)
        self.assertEqual(MarketSide.BUY, trades[0].side)
        self.assertEqual(MarketSide.SELL, trades[1].side)
        self.assertEqual(100.0, trades[0].price)
        self.assertEqual(self.start, trades[0].transaction_time)

    async def test_download_market_trades_only_reads_the_range_asked_for(self):
        """
        A recording holds a whole session. Replaying a slice of it must not
        pay for the rest: the range is filtered in SQL, not afterwards.
        """
        self.record(100)

        trades = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start + timedelta(minutes=10),
            end_time=self.start + timedelta(minutes=14),
        )

        # Inclusive at both ends, matching HistoricalFeed's own filter
        self.assertEqual([11, 12, 13, 14, 15], [t.trade_id for t in trades])

    async def test_download_market_trades_returns_them_in_order(self):
        self.record(50)
        with sqlite3.connect(self.database_filepath) as conn:
            conn.execute(
                f'INSERT INTO "{self.TABLE}" VALUES '
                "(999,'c','BTC/USD','m','t','buy',1.0,0.0,1.0,?)",
                ((self.start + timedelta(seconds=90)).timestamp(),),
            )

        trades = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start,
            end_time=self.start + timedelta(hours=1),
        )

        times = [t.transaction_time for t in trades]
        self.assertEqual(sorted(times), times)

    async def test_download_market_trades_is_cached(self):
        self.record(3)
        first = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start,
            end_time=self.start + timedelta(minutes=10),
        )

        # Nothing is read a second time, so the table is not needed again
        with sqlite3.connect(self.database_filepath) as conn:
            conn.execute(f'DROP TABLE "{self.TABLE}"')

        second = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start,
            end_time=self.start + timedelta(minutes=10),
        )
        self.assertEqual(first, second)

    async def test_cache_is_not_shared_between_sources(self):
        """
        One cache serves every data source, so a replay from a recording
        must not be handed trades downloaded from an exchange.
        """

        class OtherSource(IDataSource):
            async def download_market_trades(
                self, symbol, start_time, end_time
            ):
                raise NotImplementedError

        args = ("BTC/USD", self.start, self.start + timedelta(minutes=10))
        self.assertNotEqual(
            self.data_source.cache_key(*args), OtherSource().cache_key(*args)
        )

    async def test_start_and_end_time(self):
        self.record(10)

        self.assertEqual(self.start, self.data_source.start_time())
        self.assertEqual(
            self.start + timedelta(minutes=9), self.data_source.end_time()
        )

    async def test_start_time_without_any_recorded_trades(self):
        with self.assertRaises(ValueError):
            self.data_source.start_time()

    async def test_indexes_transaction_time(self):
        """
        Both the range query and the bounds are ordered by transaction_time,
        so the recording gets an index the first time it is opened.
        """
        self.record(3)
        self.data_source.start_time()

        with sqlite3.connect(self.database_filepath) as conn:
            indexes = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name=?",
                    (self.TABLE,),
                )
            ]

        self.assertIn(f"ix_{self.TABLE}_transaction_time", indexes)

    async def test_works_on_a_read_only_recording(self):
        """
        The index is an optimisation; a recording that cannot be written to
        still replays.
        """
        self.record(3)
        os.chmod(self.database_filepath, 0o444)
        try:
            trades = await self.data_source.download_market_trades(
                symbol="BTC/USD",
                start_time=self.start,
                end_time=self.start + timedelta(minutes=10),
            )
        finally:
            os.chmod(self.database_filepath, 0o644)

        self.assertEqual(3, len(trades))
