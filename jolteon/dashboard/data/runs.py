"""Reconstructs the engine runs a recording holds.

One engine process trades one symbol, and each run it makes is recorded
under a run id every other row is stamped with.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from jolteon.dashboard.data.sqlite import database_exists, read_table


@dataclass(frozen=True)
class RecordedEngineRun:
    """One EngineRun as the dashboard reads it back from a recording."""

    run_id: str
    exchange: str
    symbol: str
    started_at: datetime
    ended_at: datetime | None
    status: str


def _recorded_datetime(value) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


def engine_runs(db_path: str) -> list[RecordedEngineRun]:
    """Every recorded run, newest first, as "stopped", "interrupted" or
    "open".

    A run with no recorded end that a later run supersedes was
    interrupted: one engine trades one symbol, so the next run starting
    is proof this one is gone. The newest such run is only "open" - a
    process that dies never records its own end, so the recording alone
    cannot tell it from one still going.
    """
    if not database_exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = pd.read_sql(
            "SELECT run_id, exchange, symbol, started_at, ended_at "
            'FROM "engine_run" ORDER BY started_at DESC, rowid DESC',
            conn,
        )
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return []
    finally:
        conn.close()

    result = []
    for position, (_, row) in enumerate(rows.iterrows()):
        ended = _recorded_datetime(row["ended_at"])
        if ended is not None:
            status = "stopped"
        elif position == 0:
            status = "open"
        else:
            status = "interrupted"
        started = _recorded_datetime(row["started_at"])
        if started is None:
            continue
        result.append(
            RecordedEngineRun(
                run_id=str(row["run_id"]),
                exchange=str(row["exchange"]),
                symbol=str(row["symbol"]),
                started_at=started,
                ended_at=ended,
                status=status,
            )
        )
    return result


def latest_engine_run(db_path: str) -> RecordedEngineRun | None:
    """The newest engine process recorded in this database."""
    runs = engine_runs(db_path)
    return runs[0] if runs else None


def read_run_table(
    db_path: str, table: str, run_id: str | None
) -> pd.DataFrame:
    """A cached table restricted to one engine run when one is known."""
    frame = read_table(db_path, table)
    if run_id is None:
        return frame
    if "run_id" not in frame.columns:
        return frame.iloc[0:0].copy(deep=False)
    return frame[frame["run_id"] == run_id].copy(deep=False)
