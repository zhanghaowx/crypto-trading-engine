import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from jolteon.dashboard.data.runs import (
    engine_runs,
    latest_engine_run,
    read_run_table,
)


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


def test_engine_runs_read_back_how_a_run_executed(tmp_path):
    db_path = str(tmp_path / "modes.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL, execution_mode TEXT, "
            "market_data_mode TEXT)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES "
            "(?, 'Binance.US', 'BTC/USD', ?, ?, ?, ?)",
            [
                ("run-paper", 1.0, 2.0, "SIMULATED", "REALTIME"),
                ("run-replay", 3.0, 4.0, "SIMULATED", "RECORDED"),
                ("run-live", 5.0, 6.0, "REAL", "REALTIME"),
            ],
        )
        conn.commit()

    by_id = {run.run_id: run for run in engine_runs(db_path)}

    assert (
        by_id["run-paper"].execution_mode,
        by_id["run-paper"].market_data_mode,
    ) == ("SIMULATED", "REALTIME")
    assert by_id["run-replay"].market_data_mode == "RECORDED"
    assert by_id["run-live"].execution_mode == "REAL"


def test_a_run_recorded_before_modes_existed_reads_back_unclassified(tmp_path):
    """The engine_run table a previous engine wrote has neither mode
    column, and such a run must not be counted as either mode."""
    db_path = str(tmp_path / "legacy.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES "
            "('run-old', 'Kraken', 'BTC/USD', 1.0, 2.0)"
        )
        conn.commit()

    run = engine_runs(db_path)[0]

    assert run.execution_mode == "UNKNOWN"
    assert run.market_data_mode == "UNKNOWN"


def test_a_run_whose_modes_were_never_written_reads_back_unclassified(
    tmp_path,
):
    """The columns exist because a later run wrote them, and this row's
    are NULL."""
    db_path = str(tmp_path / "mixed.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL, execution_mode TEXT, "
            "market_data_mode TEXT)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES "
            "('run-old', 'Kraken', 'BTC/USD', 1.0, 2.0, NULL, NULL)"
        )
        conn.commit()

    run = engine_runs(db_path)[0]

    assert run.execution_mode == "UNKNOWN"
    assert run.market_data_mode == "UNKNOWN"


def test_engine_runs_read_back_where_a_replay_read_its_data(tmp_path):
    db_path = str(tmp_path / "replay.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL, execution_mode TEXT, "
            "market_data_mode TEXT, market_data_source TEXT, "
            "source_run_id TEXT, market_data_started_at REAL, "
            "market_data_ended_at REAL, market_data_trade_count INTEGER)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES "
            "(?, 'Kraken', 'BTC/USD', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "run-replay",
                    1000.0,
                    1100.0,
                    "SIMULATED",
                    "RECORDED",
                    "/recordings/live.sqlite",
                    "run-source",
                    10.0,
                    20.0,
                    4211,
                ),
                (
                    "run-live",
                    2000.0,
                    2100.0,
                    "SIMULATED",
                    "REALTIME",
                    "",
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )
        conn.commit()

    by_id = {run.run_id: run for run in engine_runs(db_path)}

    replay = by_id["run-replay"]
    assert replay.market_data_source == "/recordings/live.sqlite"
    assert replay.source_run_id == "run-source"
    assert replay.market_data_started_at == datetime(
        1970, 1, 1, 0, 0, 10, tzinfo=timezone.utc
    )
    assert replay.market_data_ended_at == datetime(
        1970, 1, 1, 0, 0, 20, tzinfo=timezone.utc
    )
    assert replay.market_data_trade_count == 4211

    live = by_id["run-live"]
    assert live.market_data_source == ""
    assert live.source_run_id is None
    assert live.market_data_started_at is None
    assert live.market_data_trade_count is None


def test_a_run_recorded_before_provenance_existed_reads_back_without_it(
    tmp_path,
):
    db_path = str(tmp_path / "legacy-provenance.sqlite")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES "
            "('run-old', 'Kraken', 'BTC/USD', 1.0, 2.0)"
        )
        conn.commit()

    run = engine_runs(db_path)[0]

    assert run.market_data_source == ""
    assert run.source_run_id is None
    assert run.market_data_started_at is None
    assert run.market_data_ended_at is None
    assert run.market_data_trade_count is None
