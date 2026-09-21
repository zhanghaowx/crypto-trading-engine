import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import pandas as pd
from streamlit.testing.v1 import AppTest

from jolteon.app.data import (
    count_matching,
    engine_runs,
    ensure_fair_price_lookup_index,
    last_rowid_where,
    latest_engine_run,
    max_rowid,
    read_after,
    read_fair_prices_for_fills,
    read_latest_per_group,
    read_latest_row,
    read_run_table,
    read_table,
    reset_table_cache,
)


class TestReadTable(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

        self.write(
            'CREATE TABLE "order" (client_order_id TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('1', 100.0)",
        )

        # Rows already read are held in the session, which outlives a test
        reset_table_cache()

    def tearDown(self):
        reset_table_cache()
        self._tmpdir.cleanup()

    def write(self, *statements: str, db_path: str | None = None) -> None:
        """
        Run each statement against the database and close the connection.

        Windows refuses to remove a file that is still open, so a
        connection left for the garbage collector to close fails the
        temporary directory's cleanup in tearDown.
        """
        with closing(sqlite3.connect(db_path or self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def insert(self, client_order_id: str, price: float) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                'INSERT INTO "order" VALUES (?, ?)', (client_order_id, price)
            )
            conn.commit()

    def test_reads_table_named_after_a_reserved_sql_keyword(self):
        # "order" is a reserved SQL keyword; an unquoted "SELECT * FROM
        # order" fails as a syntax error rather than returning rows.
        df = read_table(self.db_path, "order")

        self.assertEqual(1, len(df))
        self.assertEqual("1", df.iloc[0]["client_order_id"])

    def test_missing_table_returns_empty_dataframe(self):
        df = read_table(self.db_path, "does_not_exist")

        self.assertTrue(df.empty)

    def test_missing_database_file_returns_empty_dataframe(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        df = read_table(missing_path, "order")

        self.assertTrue(df.empty)

    def test_returns_rows_added_since_the_last_read(self):
        self.assertEqual(1, len(read_table(self.db_path, "order")))

        self.insert("2", 200.0)
        self.insert("3", 300.0)

        df = read_table(self.db_path, "order")
        self.assertEqual(["1", "2", "3"], list(df["client_order_id"]))
        self.assertEqual([100.0, 200.0, 300.0], list(df["price"]))

    def test_does_not_re_read_rows_it_already_has(self):
        """
        The whole point is that rows already fetched are not fetched again,
        which is visible as an edit to an old row not being picked up.
        """
        read_table(self.db_path, "order")

        self.write('UPDATE "order" SET price = 999.0')
        self.insert("2", 200.0)

        df = read_table(self.db_path, "order")
        # The stale row keeps its original price; only the new row is read
        self.assertEqual([100.0, 200.0], list(df["price"]))

    def test_reads_a_table_with_a_primary_key_in_full(self):
        """
        A row under a primary key is rewritten in place, and an update
        leaves the row id alone, so such a table cannot be read forward.
        """
        self.write(
            "CREATE TABLE candle (start_time REAL PRIMARY KEY, close REAL)",
            "INSERT INTO candle VALUES (1.0, 100.0)",
        )

        self.assertEqual(
            [100.0], list(read_table(self.db_path, "candle")["close"])
        )

        self.write("UPDATE candle SET close = 150.0 WHERE start_time = 1")

        # The update to the open candle is picked up, not missed
        self.assertEqual(
            [150.0], list(read_table(self.db_path, "candle")["close"])
        )

    def test_starts_over_when_the_recording_is_replaced(self):
        """
        Restarting the engine onto a fresh database restarts the row ids,
        so rows already held would otherwise mask the new recording.
        """
        self.insert("2", 200.0)
        self.assertEqual(2, len(read_table(self.db_path, "order")))

        self.write('DELETE FROM "order"')
        self.insert("fresh", 1.0)

        df = read_table(self.db_path, "order")
        self.assertEqual(["fresh"], list(df["client_order_id"]))

    def test_each_database_is_tracked_separately(self):
        other_path = str(Path(self._tmpdir.name) / "other.sqlite")
        self.write(
            'CREATE TABLE "order" (client_order_id TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('other', 1.0)",
            db_path=other_path,
        )

        self.assertEqual(
            ["1"], list(read_table(self.db_path, "order")["client_order_id"])
        )
        self.assertEqual(
            ["other"],
            list(read_table(other_path, "order")["client_order_id"]),
        )

    def test_caller_may_add_columns_without_affecting_the_next_read(self):
        df = read_table(self.db_path, "order")
        df["time"] = 0

        self.assertNotIn("time", read_table(self.db_path, "order").columns)

    @mock.patch("jolteon.app.data._MAX_CACHED_ROWS", 2)
    def test_caps_cached_rows_to_bound_session_memory(self):
        self.insert("2", 200.0)
        self.insert("3", 300.0)

        df = read_table(self.db_path, "order")

        self.assertEqual(["2", "3"], list(df["client_order_id"]))


class TestReadLatestRow(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def write(self, *statements: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def test_missing_database_file_returns_none(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        self.assertIsNone(read_latest_row(missing_path, "bbo_feed"))

    def test_missing_table_returns_none(self):
        self.write("CREATE TABLE other (a INTEGER)")

        self.assertIsNone(read_latest_row(self.db_path, "does_not_exist"))

    def test_returns_only_the_most_recently_inserted_row(self):
        self.write(
            "CREATE TABLE bbo_feed (price REAL)",
            "INSERT INTO bbo_feed VALUES (1.0)",
            "INSERT INTO bbo_feed VALUES (2.0)",
        )

        row = read_latest_row(self.db_path, "bbo_feed")

        self.assertEqual(2.0, row["price"])


class TestReadLatestPerGroup(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "test.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def write(self, *statements: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def test_missing_database_file_returns_empty_dataframe(self):
        missing_path = str(Path(self._tmpdir.name) / "missing.sqlite")

        df = read_latest_per_group(missing_path, "heartbeat", "sender")

        self.assertTrue(df.empty)

    def test_missing_table_returns_empty_dataframe(self):
        self.write("CREATE TABLE other (a INTEGER)")

        df = read_latest_per_group(self.db_path, "does_not_exist", "sender")

        self.assertTrue(df.empty)

    def test_returns_the_latest_row_for_each_distinct_group_value(self):
        self.write(
            'CREATE TABLE "order" (side TEXT, price REAL)',
            "INSERT INTO \"order\" VALUES ('BUY', 1.0)",
            "INSERT INTO \"order\" VALUES ('BUY', 2.0)",
            "INSERT INTO \"order\" VALUES ('SELL', 3.0)",
        )

        df = read_latest_per_group(self.db_path, "order", "side")

        self.assertEqual(
            {"BUY": 2.0, "SELL": 3.0}, dict(zip(df["side"], df["price"]))
        )


class TestCountMatching(unittest.TestCase):
    """
    The navigation asks every engine how many errors it has logged, and
    the log is the largest table recorded, so it is counted in the
    database rather than read out of it.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmpdir.name) / "logs.sqlite")

    def tearDown(self):
        self._tmpdir.cleanup()

    def write(self, *statements: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for statement in statements:
                conn.execute(statement)
            conn.commit()

    def test_counts_only_the_levels_asked_about(self):
        self.write(
            "CREATE TABLE logs (levelname TEXT)",
            "INSERT INTO logs VALUES ('ERROR')",
            "INSERT INTO logs VALUES ('CRITICAL')",
            "INSERT INTO logs VALUES ('INFO')",
        )

        found = count_matching(
            self.db_path, "logs", "levelname", ("ERROR", "CRITICAL")
        )

        self.assertEqual(2, found)

    def test_a_log_nothing_has_written_yet_counts_nothing(self):
        """
        The dashboard is often open before the first engine starts, which
        is an ordinary state rather than a failure.
        """
        found = count_matching(
            self.db_path, "logs", "levelname", ("ERROR", "CRITICAL")
        )

        self.assertEqual(0, found)

    def test_a_database_without_the_table_counts_nothing(self):
        self.write("CREATE TABLE other (a INTEGER)")

        found = count_matching(
            self.db_path, "logs", "levelname", ("ERROR", "CRITICAL")
        )

        self.assertEqual(0, found)


def keyed_table_script():
    import streamlit as st

    from jolteon.app.data import read_table

    fills = read_table(st.session_state.db_path, "decorated_order_fill")
    st.write(f"{len(fills)}|" + ",".join(str(v) for v in fills["fee"]))


def _keyed_db(tmp_path, rows) -> str:
    db_path = str(tmp_path / "keyed.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(exchange_execution_id TEXT PRIMARY KEY, fee REAL)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _write(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def test_a_rewritten_row_in_a_keyed_table_is_read_again(tmp_path):
    """A keyed row may be rewritten in place, so recent rows have to be
    read again rather than blindly carried over from the last refresh."""
    db_path = _keyed_db(tmp_path, [("a", 1.0), ("b", 2.0)])

    at = AppTest.from_function(keyed_table_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "2|1.0,2.0"

    _write(
        db_path,
        "UPDATE decorated_order_fill SET fee = 9.0 WHERE "
        "exchange_execution_id = 'b'",
    )
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "2|1.0,9.0"


def test_rows_added_to_a_keyed_table_arrive(tmp_path):
    db_path = _keyed_db(tmp_path, [("a", 1.0)])

    at = AppTest.from_function(keyed_table_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "1|1.0"

    _write(db_path, "INSERT INTO decorated_order_fill VALUES ('b', 2.0)")
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "2|1.0,2.0"


def test_a_replaced_keyed_recording_is_read_from_scratch(tmp_path):
    """Row ids start over when the recording is replaced, and the rows
    held from the old one describe a session that is gone."""
    db_path = _keyed_db(tmp_path, [("a", 1.0), ("b", 2.0), ("c", 3.0)])

    at = AppTest.from_function(keyed_table_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "3|1.0,2.0,3.0"

    _write(db_path, "DELETE FROM decorated_order_fill")
    _write(db_path, "INSERT INTO decorated_order_fill VALUES ('z', 7.0)")
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "1|7.0"


def test_a_keyed_table_longer_than_the_cache_keeps_its_newest_rows(tmp_path):
    """The cache is bounded, so a recording that outgrows it holds the
    most recent rows rather than the first ones read."""
    db_path = _keyed_db(tmp_path, [(str(i), float(i)) for i in range(6)])

    at = AppTest.from_function(keyed_table_script)
    at.session_state["db_path"] = db_path
    with mock.patch("jolteon.app.data._MAX_CACHED_ROWS", 4):
        at.run()

    assert not at.exception
    assert at.markdown[-1].value == "4|2.0,3.0,4.0,5.0"


def test_reading_after_a_row_holds_still_when_nothing_was_added():
    """A refresh that finds no new rows must leave the caller's place in
    the recording where it was."""
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "feed.sqlite")
        conn = sqlite3.connect(db_path)
        with closing(conn):
            conn.execute("CREATE TABLE feed (value REAL)")
            conn.execute("INSERT INTO feed VALUES (1.0)")
            conn.commit()

        frame, at = read_after(db_path, "feed", 0)
        assert list(frame["value"]) == [1.0]
        assert at == 1

        frame, still = read_after(db_path, "feed", at)
        assert frame.empty
        assert still == at


def test_reading_a_recording_that_is_not_there_finds_nothing():
    missing = str(Path(tempfile.gettempdir()) / "jolteon-absent.sqlite")

    frame, at = read_after(missing, "feed", 0)
    assert frame.empty
    assert at == 0
    assert last_rowid_where(missing, "feed", "flag") is None


def test_a_table_the_recording_does_not_have_finds_nothing():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "empty.sqlite")
        sqlite3.connect(db_path).close()

        frame, at = read_after(db_path, "feed", 7)
        assert frame.empty
        assert at == 7
        assert last_rowid_where(db_path, "feed", "flag") is None


def test_the_highest_row_id_of_a_table_that_is_not_there_is_zero():
    """A recording that has not been written yet, or one without the
    table asked about, has no row to be the highest."""
    missing = str(Path(tempfile.gettempdir()) / "jolteon-no-such.sqlite")
    assert max_rowid(missing, "decorated_order_fill") == 0

    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "bare.sqlite")
        sqlite3.connect(db_path).close()
        assert max_rowid(db_path, "decorated_order_fill") == 0


def test_the_highest_row_id_counts_up_with_the_rows():
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder) / "feed.sqlite")
        conn = sqlite3.connect(db_path)
        with closing(conn):
            conn.execute("CREATE TABLE feed (value REAL)")
            conn.executemany("INSERT INTO feed VALUES (?)", [(1.0,), (2.0,)])
            conn.commit()

        assert max_rowid(db_path, "feed") == 2


def test_reads_only_fair_prices_needed_for_visible_fill_markouts(tmp_path):
    db_path = str(tmp_path / "prices.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price ("
            "timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)",
            [
                (1.0, "BTC/USD", "AdjustedFairPriceModel", 99.0, 101.0),
                (9.5, "BTC/USD", "AdjustedFairPriceModel", 100.0, 102.0),
                (10.0, "BTC/USD", "MidPriceFairPriceModel", 500.0, 502.0),
                (11.0, "ETH/USD", "AdjustedFairPriceModel", 50.0, 52.0),
                (40.5, "BTC/USD", "AdjustedFairPriceModel", 103.0, 105.0),
                (50.0, "BTC/USD", "AdjustedFairPriceModel", 104.0, 106.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    fills = pd.DataFrame(
        [
            {
                "timestamp": 10.0,
                "symbol": "BTC/USD",
                "fair_price_model": "AdjustedFairPriceModel",
            }
        ]
    )
    rows = read_fair_prices_for_fills(
        db_path,
        fills,
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    )

    assert list(rows["timestamp"]) == [9.5, 40.5]
    assert set(rows["model"]) == {"AdjustedFairPriceModel"}
    assert set(rows["symbol"]) == {"BTC/USD"}


def test_fair_prices_are_not_read_without_a_fill_to_read_them_for(tmp_path):
    db_path = str(tmp_path / "fair.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price (timestamp REAL, symbol TEXT, "
            "model TEXT, bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.commit()
    finally:
        conn.close()

    unusable = pd.DataFrame(
        [{"timestamp": None, "symbol": None, "fair_price_model": None}]
    )

    assert read_fair_prices_for_fills(
        db_path, unusable, max_horizon_seconds=30.0, max_lag_seconds=1.0
    ).empty


def test_fair_prices_from_a_recording_without_the_table_are_nothing(tmp_path):
    """A recording made before fair prices were recorded should leave the
    markout columns empty rather than take the page down."""
    db_path = str(tmp_path / "no_fair_price.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE other (x REAL)")
        conn.commit()
    finally:
        conn.close()

    fills = pd.DataFrame(
        [
            {
                "timestamp": 10.0,
                "symbol": "BTC/USD",
                "fair_price_model": "MidPriceFairPriceModel",
            }
        ]
    )

    assert read_fair_prices_for_fills(
        db_path, fills, max_horizon_seconds=30.0, max_lag_seconds=1.0
    ).empty


def test_the_fair_price_index_is_made_once_and_survives_a_locked_recording(
    tmp_path,
):
    missing = str(tmp_path / "absent.sqlite")
    assert not ensure_fair_price_lookup_index(missing)

    db_path = str(tmp_path / "indexed.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price (timestamp REAL, symbol TEXT, "
            "model TEXT, bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.commit()
    finally:
        conn.close()

    assert ensure_fair_price_lookup_index(db_path)
    # Asked a second time, the answer comes from what this process
    # already did rather than from the recording.
    assert ensure_fair_price_lookup_index(db_path)

    conn = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    finally:
        conn.close()
    assert "jolteon_fair_price_lookup" in names


def test_a_recording_with_no_fair_prices_cannot_be_indexed(tmp_path):
    db_path = str(tmp_path / "unindexable.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE other (x REAL)")
        conn.commit()
    finally:
        conn.close()

    assert not ensure_fair_price_lookup_index(db_path)


def test_fair_prices_are_not_read_for_fills_that_name_no_model(tmp_path):
    db_path = str(tmp_path / "prices.sqlite")

    assert read_fair_prices_for_fills(
        db_path,
        pd.DataFrame(),
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    ).empty
    assert read_fair_prices_for_fills(
        db_path,
        pd.DataFrame([{"timestamp": 10.0, "symbol": "BTC/USD"}]),
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    ).empty


def test_engine_runs_identify_latest_stopped_and_interrupted(tmp_path):
    db_path = str(tmp_path / "runs.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES (?, 'Binance.US', 'BTC/USD', ?, ?)",
            [
                ("run-a", 1.0, None),
                ("run-b", 2.0, 3.0),
                ("run-c", 4.0, None),
            ],
        )
        conn.commit()

    runs = engine_runs(db_path)

    assert [run.run_id for run in runs] == ["run-c", "run-b", "run-a"]
    assert [run.status for run in runs] == [
        "open",
        "stopped",
        "interrupted",
    ]
    assert latest_engine_run(db_path) == runs[0]


def test_engine_runs_skip_a_row_without_a_start_time(tmp_path):
    db_path = str(tmp_path / "partial.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES (?, 'Binance.US', 'BTC/USD', ?, ?)",
            [
                ("run-dated", 1.0, None),
                ("run-undated", None, None),
            ],
        )
        conn.commit()

    assert [run.run_id for run in engine_runs(db_path)] == ["run-dated"]


def test_latest_engine_run_is_absent_without_run_metadata(tmp_path):
    db_path = str(tmp_path / "empty.sqlite")
    sqlite3.connect(db_path).close()

    assert latest_engine_run(db_path) is None


def test_read_run_table_returns_only_the_named_run(tmp_path):
    db_path = str(tmp_path / "events.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE event (run_id TEXT, value INTEGER)")
        conn.executemany(
            "INSERT INTO event VALUES (?, ?)",
            [("run-a", 1), ("run-b", 2)],
        )
        conn.commit()

    frame = read_run_table(db_path, "event", "run-b")

    assert list(frame["value"]) == [2]


def test_read_after_can_be_scoped_to_a_run(tmp_path):
    db_path = str(tmp_path / "after.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE event (run_id TEXT, value INTEGER)")
        conn.executemany(
            "INSERT INTO event VALUES (?, ?)",
            [("run-a", 1), ("run-b", 2), ("run-b", 3)],
        )
        conn.commit()

    frame, at = read_after(db_path, "event", 0, run_id="run-b")

    assert list(frame["value"]) == [2, 3]
    assert at == 3


def test_latest_per_group_can_be_scoped_to_a_run(tmp_path):
    db_path = str(tmp_path / "latest-run.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            'CREATE TABLE "order" (run_id TEXT, side TEXT, price REAL)'
        )
        conn.executemany(
            'INSERT INTO "order" VALUES (?, ?, ?)',
            [
                ("run-a", "BUY", 1.0),
                ("run-b", "BUY", 2.0),
                ("run-a", "SELL", 3.0),
                ("run-b", "SELL", 4.0),
            ],
        )
        conn.commit()

    frame = read_latest_per_group(db_path, "order", "side", run_id="run-b")

    assert dict(zip(frame["side"], frame["price"])) == {
        "BUY": 2.0,
        "SELL": 4.0,
    }
