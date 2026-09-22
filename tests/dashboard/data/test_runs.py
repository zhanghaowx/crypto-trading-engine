import sqlite3
from contextlib import closing

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
