"""Identity and metadata for one engine process lifetime."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

_ID_TIME_FORMAT = "%Y%m%dT%H%M%SZ"


def engine_run_id(started_at: datetime) -> str:
    """A unique run id that remains readable and sorts by start time."""
    return f"{started_at.strftime(_ID_TIME_FORMAT)}-{uuid.uuid4().hex[:8]}"


class ExecutionMode(StrEnum):
    """Where a run's orders went."""

    SIMULATED = "SIMULATED"
    REAL = "REAL"
    # What a run records when nothing it was wired with claimed a mode,
    # and what a run recorded before runs claimed one reads back as. Kept
    # as a value of its own so such a run is unclassified rather than
    # quietly counted as simulated.
    UNKNOWN = "UNKNOWN"


class MarketDataMode(StrEnum):
    """Whether a run's market data arrived as it happened or was played
    back from something already recorded."""

    REALTIME = "REALTIME"
    RECORDED = "RECORDED"
    UNKNOWN = "UNKNOWN"


def execution_mode_of(service: object) -> ExecutionMode:
    """
    Returns: The mode an execution service claims, and UNKNOWN from one
    that claims nothing.

    Asked of the service that actually placed the orders, so a run's
    classification cannot disagree with what executed it.
    """
    claimed = getattr(service, "execution_mode", None)
    if isinstance(claimed, ExecutionMode):
        return claimed
    return ExecutionMode.UNKNOWN


def market_data_mode_of(feed: object) -> MarketDataMode:
    """
    Returns: The mode a market data feed claims, and UNKNOWN from one
    that claims nothing.
    """
    claimed = getattr(feed, "market_data_mode", None)
    if isinstance(claimed, MarketDataMode):
        return claimed
    return MarketDataMode.UNKNOWN


@dataclass
class EngineRun:
    """One engine process, from start until stop or interruption.

    How the run executed and where its market data came from are two
    independent facts, and neither follows from whether the run
    finished: live paper trading and a replay of a recording both
    simulate execution, and either can be stopped or killed.

    `started_at` and `ended_at` are this run's own, taken from the
    machine's clock. A replay moves the engine's clock through the
    interval it is replaying, which the market_data_ fields hold
    separately - so a replay says both when it ran and what it read.
    """

    PRIMARY_KEY = "run_id"

    run_id: str
    exchange: str
    symbol: str
    started_at: datetime
    ended_at: datetime | None = None
    execution_mode: ExecutionMode = ExecutionMode.UNKNOWN
    market_data_mode: MarketDataMode = MarketDataMode.UNKNOWN
    market_data_source: str = ""
    source_run_id: str | None = None
    market_data_started_at: datetime | None = None
    market_data_ended_at: datetime | None = None
    market_data_trade_count: int | None = None
