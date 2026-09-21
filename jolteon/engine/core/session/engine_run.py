"""One process lifetime, named so a restart is visible in the recording.

A trading session spans however many engine runs happened that day. The
run is what operational questions are asked of - where the market data
stopped, which orders a process left behind - while the session is what
strategy performance is measured over, so neither can stand in for the
other.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"


def engine_run_id(started_at: datetime) -> str:
    """
    Returns: An id for a run that started at `started_at`, unique across
    processes and sorting in the order the runs started.
    """
    return f"{started_at.strftime(_ID_TIME_FORMAT)}-{uuid.uuid4().hex[:8]}"


@dataclass
class EngineRun:
    """One engine process, from start to whatever ended it.

    `ended_at` stays empty for a run still trading, and for one that was
    killed before it could record its own end - which is what makes a
    crash visible after the fact.
    """

    PRIMARY_KEY = "run_id"

    run_id: str
    exchange: str
    symbol: str
    started_at: datetime
    ended_at: datetime | None = None
