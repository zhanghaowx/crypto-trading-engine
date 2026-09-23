import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.core.events import Events
from jolteon.engine.market_data.core.order_book import BookModel
from jolteon.engine.market_data.data_source import (
    DatabaseDataSource,
    IDataSource,
)


class TestDatabaseDataSource(unittest.IsolatedAsyncioTestCase):
    TABLE = Events().market_trade.name
    BOOK_TABLE = Events().order_book_update.name

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
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{self.TABLE}" ('
                "exchange_trade_id, client_order_id, symbol, maker_order_id, "
                "taker_order_id, side, price, fee, quantity, "
                "transaction_time)"
            )
            conn.executemany(
                f'INSERT INTO "{self.TABLE}" VALUES (?,?,?,?,?,?,?,?,?,?)',
                rows,
            )
            conn.commit()

    async def test_download_market_trades(self):
        self.record(3)

        trades = await self.data_source.download_market_trades(
            symbol="BTC/USD",
            start_time=self.start,
            end_time=self.start + timedelta(minutes=10),
        )

        self.assertEqual(3, len(trades))
        self.assertEqual([1, 2, 3], [t.exchange_trade_id for t in trades])
        self.assertEqual("BTC/USD", trades[0].symbol)
        self.assertEqual(MarketSide.BUY, trades[0].side)
        self.assertEqual(MarketSide.SELL, trades[1].side)
        self.assertEqual(100.0, trades[0].price)
        self.assertEqual(self.start, trades[0].transaction_time)

    async def test_downloads_compact_book_updates(self):
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(
                f'CREATE TABLE "{self.BOOK_TABLE}" ('
                "symbol, model, version, sequence, bids, asks, is_snapshot, "
                "exchange_time)"
            )
            conn.execute(
                f'INSERT INTO "{self.BOOK_TABLE}" VALUES (?,?,?,?,?,?,?,?)',
                (
                    "BTC/USD",
                    "l2",
                    1,
                    7,
                    "[[100.0,2.0]]",
                    "[[101.0,3.0]]",
                    1,
                    self.start.timestamp(),
                ),
            )
            conn.commit()

        records = await self.data_source.download_order_book_updates(
            "BTC/USD", self.start, self.start + timedelta(seconds=1)
        )

        self.assertEqual(1, len(records))
        self.assertEqual(BookModel.L2, records[0].model)
        self.assertEqual(7, records[0].sequence)
        self.assertEqual(2.0, records[0].to_update().bids[0].quantity)

    async def test_legacy_recording_has_no_book_updates(self):
        self.record(1)

        records = await self.data_source.download_order_book_updates(
            "BTC/USD", self.start, self.start + timedelta(seconds=1)
        )

        self.assertEqual([], records)

    async def test_malformed_book_table_reports_its_schema_error(self):
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(f'CREATE TABLE "{self.BOOK_TABLE}" (symbol)')
            conn.commit()

        with self.assertRaisesRegex(
            sqlite3.OperationalError, "no such column"
        ):
            await self.data_source.download_order_book_updates(
                "BTC/USD", self.start, self.start + timedelta(seconds=1)
            )

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

        # Inclusive at both ends, matching ReplayMarketDataFeed's filter
        self.assertEqual(
            [11, 12, 13, 14, 15], [t.exchange_trade_id for t in trades]
        )

    async def test_download_market_trades_returns_them_in_order(self):
        self.record(50)
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(
                f'INSERT INTO "{self.TABLE}" VALUES '
                "(999,'c','BTC/USD','m','t','buy',1.0,0.0,1.0,?)",
                ((self.start + timedelta(seconds=90)).timestamp(),),
            )
            conn.commit()

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
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(f'DROP TABLE "{self.TABLE}"')
            conn.commit()

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

    async def test_start_time_with_an_empty_market_trade_table(self):
        """A recording may hold the table but no trades, e.g. a run that
        was stopped before the first trade arrived."""
        self.record(0)

        with self.assertRaises(ValueError):
            self.data_source.start_time()

    async def test_indexes_transaction_time(self):
        """
        Both the range query and the bounds are ordered by transaction_time,
        so the recording gets an index the first time it is opened.
        """
        self.record(3)
        self.data_source.start_time()

        with closing(sqlite3.connect(self.database_filepath)) as conn:
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


class TestReplayInput(unittest.IsolatedAsyncioTestCase):
    """What a replay records about the data it read, so a later reader can
    tell which recording and which slice of it produced a run."""

    TABLE = Events().market_trade.name

    async def asyncSetUp(self):
        self.database_filepath = (
            f"{tempfile.gettempdir()}/{uuid.uuid4()}.sqlite"
        )
        self.start = datetime(2022, 1, 1, 10, 0, 0, tzinfo=pytz.utc)
        self.end = self.start + timedelta(hours=1)
        self.data_source = DatabaseDataSource(self.database_filepath)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.database_filepath + suffix
            if os.path.exists(path):
                os.remove(path)

    def record(self, runs: list[str], with_run_column: bool = True):
        """One market trade per entry in `runs`, a minute apart."""
        run_column = ", run_id" if with_run_column else ""
        placeholder = ", ?" if with_run_column else ""
        with closing(sqlite3.connect(self.database_filepath)) as conn:
            conn.execute(
                f'CREATE TABLE "{self.TABLE}" (transaction_time{run_column})'
            )
            conn.executemany(
                f'INSERT INTO "{self.TABLE}" VALUES (?{placeholder})',
                [
                    (
                        (self.start + timedelta(minutes=i)).timestamp(),
                        *((run,) if with_run_column else ()),
                    )
                    for i, run in enumerate(runs)
                ],
            )
            conn.commit()

    async def test_a_recording_is_named_by_its_resolved_path(self):
        self.record(["run-a"])

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertEqual(
            str(Path(self.database_filepath).resolve()), replay_input.source
        )

    async def test_the_run_that_recorded_the_interval_is_reported(self):
        self.record(["run-a", "run-a", "run-a"])

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertEqual("run-a", replay_input.source_run_id)
        self.assertEqual(3, replay_input.trade_count)

    async def test_an_interval_spanning_several_runs_names_none_of_them(self):
        self.record(["run-a", "run-b"])

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertIsNone(replay_input.source_run_id)
        self.assertEqual(2, replay_input.trade_count)

    async def test_only_the_interval_asked_for_is_counted(self):
        """The same recording replayed twice over two intervals has to be
        told apart by what each replay actually read."""
        self.record(["run-a", "run-b", "run-b"])

        first = self.data_source.describe_replay_input(
            self.start, self.start + timedelta(seconds=30)
        )
        second = self.data_source.describe_replay_input(
            self.start + timedelta(minutes=1), self.end
        )

        self.assertEqual(
            ("run-a", 1), (first.source_run_id, first.trade_count)
        )
        self.assertEqual(
            ("run-b", 2), (second.source_run_id, second.trade_count)
        )

    async def test_rows_recorded_without_a_run_name_no_run(self):
        self.record(["ignored"], with_run_column=False)

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertIsNone(replay_input.source_run_id)
        self.assertEqual(1, replay_input.trade_count)

    async def test_rows_whose_run_was_never_written_name_no_run(self):
        self.record([None])

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertIsNone(replay_input.source_run_id)

    async def test_a_recording_without_market_trades_leaves_both_unanswered(
        self,
    ):
        """Replay input is recorded so a run can be traced afterwards; a
        recording it cannot be read out of must not stop the replay."""
        sqlite3.connect(self.database_filepath).close()

        replay_input = self.data_source.describe_replay_input(
            self.start, self.end
        )

        self.assertIsNone(replay_input.source_run_id)
        self.assertIsNone(replay_input.trade_count)

    async def test_a_source_with_nothing_to_say_answers_with_its_own_name(
        self,
    ):
        class RemoteSource(IDataSource):
            async def download_market_trades(
                self, symbol, start_time, end_time
            ):
                raise NotImplementedError  # pragma: no cover

        replay_input = RemoteSource().describe_replay_input(
            self.start, self.end
        )

        self.assertEqual("RemoteSource", replay_input.source)
        self.assertIsNone(replay_input.source_run_id)
        self.assertIsNone(replay_input.trade_count)
