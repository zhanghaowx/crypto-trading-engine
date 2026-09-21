"""Identity and metadata for one engine process lifetime."""

import uuid
from dataclasses import dataclass
from datetime import datetime

_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"


def engine_run_id(started_at: datetime) -> str:
    """A unique run id that remains readable and sorts by start time."""
    return f"{started_at.strftime(_ID_TIME_FORMAT)}-{uuid.uuid4().hex[:8]}"


@dataclass
class EngineRun:
    """One engine process, from start until stop or interruption."""

    PRIMARY_KEY = "run_id"

    run_id: str
    exchange: str
    symbol: str
    started_at: datetime
    ended_at: datetime | None = None
