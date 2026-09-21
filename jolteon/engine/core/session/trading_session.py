"""The accounting window every figure described as a session's is scoped to.

A recording outlives the process that writes it and may hold weeks of
trading, so "everything in the file" is not an accounting period. A
trading session is one UTC calendar day, which for a market that never
closes is the nearest thing to a trading day there is.

The boundary is an accounting one and nothing else: nothing is flattened,
cancelled or reset when a day rolls over, so inventory and strategy state
carry straight across it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SESSION_ID_FORMAT = "%Y-%m-%d"

_A_DAY = timedelta(days=1)


def trading_session_id(moment: datetime) -> str:
    """
    Returns: Which trading session `moment` falls in, as "2026-09-20".

    Sessions sort and compare as their own ids do, which is what lets a
    query ask for everything before a given session without working out
    a single date.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(SESSION_ID_FORMAT)


def trading_session_id_at(epoch_seconds: float) -> str:
    return trading_session_id(
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    )


def trading_session_window(session_id: str) -> tuple[datetime, datetime]:
    """
    Returns: When the session opens and when the next one does - the end
    is the first moment that no longer belongs to this session.
    """
    opened = datetime.strptime(session_id, SESSION_ID_FORMAT).replace(
        tzinfo=timezone.utc
    )
    return opened, opened + _A_DAY


@dataclass
class TradingSessionRun:
    """The stretch of one trading session one engine run actually traded.

    A session may be traded by several runs and a run may span several
    sessions, so this is recorded per pair rather than per session: a
    process restarting at noon must not overwrite what the morning's
    process recorded about the same day.

    Opening and closing inventory are deliberately not here. A process
    starting in the middle of a day cannot know what the day held before
    it, while the fills recorded under each session id add up to the same
    answer whichever process recorded them.
    """

    PRIMARY_KEY = "session_run_id"

    session_run_id: str
    session_id: str
    run_id: str
    exchange: str
    symbol: str
    first_seen_at: datetime
    last_seen_at: datetime

    @staticmethod
    def identity(session_id: str, run_id: str) -> str:
        return f"{session_id}@{run_id}"
