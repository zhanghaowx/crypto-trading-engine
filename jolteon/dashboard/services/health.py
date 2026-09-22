"""
Health as it stands across every engine under the root.

One engine trades one symbol and records into a directory of its own, so
a component's health is only ever half a fact: the other half is which
engine's it was. Everything here reads every engine and carries that
symbol along.
"""

import time
from dataclasses import dataclass, replace

import pandas as pd
import streamlit as st

from jolteon.dashboard.data.engines import (
    SCAN_SECONDS,
    EngineDatabase,
    engine_databases,
)
from jolteon.dashboard.data.runs import RecordedEngineRun, engine_runs
from jolteon.dashboard.data.sqlite import (
    count_matching,
    read_latest_per_group,
    read_latest_row,
    read_table,
)

# A process that dies never reports its own death - its last heartbeat row
# just stops moving, often a cheerful NORMAL one - so silence is the only
# signal the dashboard has that a background component is gone.
#
# Live components heartbeat every 10s, and each heartbeat is written out
# as it arrives, so a healthy sender looks at most one heartbeat cycle
# stale from here plus the reading page's own refresh interval. The
# timeout sits past two of those cycles; anything tighter would flag a
# running engine as down on nearly every refresh.
HEARTBEAT_TIMEOUT_SECONDS = 30

# CRITICAL is the same kind of thing an operator calls an "error" as
# ERROR is, just a more severe one. Everything below ERROR is recorded
# but deliberately never surfaced.
ERROR_LEVELS = ("ERROR", "CRITICAL")


def is_down(seconds_since_seen: float) -> bool:
    """Whether a sender has gone quiet for long enough to call it dead."""
    return seconds_since_seen > HEARTBEAT_TIMEOUT_SECONDS


def resolve_run(
    db_path: str, run: RecordedEngineRun | None
) -> RecordedEngineRun | None:
    """The same run, with an "open" status settled into "running" or
    "interrupted" by whether its engine is still heartbeating.

    Measured from the run's own start as well as its last heartbeat, so
    an engine that has only just come up is not called interrupted for
    the seconds before its first one arrives.
    """
    if run is None or run.status != "open":
        return run

    last = read_latest_row(db_path, "heartbeat")
    seen = run.started_at.timestamp()
    if last is not None:
        seen = max(seen, float(last["timestamp"]))
    quiet = is_down(time.time() - seen)
    return replace(run, status="interrupted" if quiet else "running")


def resolve_runs(db_path: str) -> list[RecordedEngineRun]:
    """Every run a recording holds, newest first, with each "open" status
    settled the way `resolve_run` settles it - so a reader picking a past
    run is told the same thing about it as a reader watching it live."""
    # `resolve_run` only answers with nothing when given nothing, which a
    # recorded run never is; the fallback is there for the type alone.
    return [resolve_run(db_path, run) or run for run in engine_runs(db_path)]


@st.cache_data(ttl=SCAN_SECONDS, show_spinner=False)
def heartbeats(root: str) -> pd.DataFrame:
    """
    The last heartbeat from every sender of every engine, each row naming
    the symbol whose engine sent it.

    A recorded heartbeat carries no symbol of its own - senders are named
    for what they do, not for what they trade - so which engine sent one
    is known only from the file it was read out of.
    """
    frames = [
        found.assign(
            symbol=engine.symbol,
            exchange=engine.exchange,
            engine_key=engine.key,
            engine_label=engine.label,
        )
        for engine, found in (
            (engine, read_latest_per_group(engine.path, "heartbeat", "sender"))
            for engine in engine_databases(root)
        )
        if not found.empty
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def errors(engines: list[EngineDatabase]) -> pd.DataFrame:
    """
    Every ERROR and CRITICAL line every engine has logged, newest first,
    each row naming the symbol whose engine logged it.

    Read through `read_table` rather than a query of its own, so a
    dashboard left open reads only the lines added since it last looked.
    """
    frames = [
        found.assign(
            symbol=engine.symbol,
            exchange=engine.exchange,
            engine_key=engine.key,
            engine_label=engine.label,
        )
        for engine, found in (
            (engine, _error_lines(engine.log_path)) for engine in engines
        )
        if not found.empty
    ]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values("created", ascending=False)


def _error_lines(log_db_path: str) -> pd.DataFrame:
    logs = read_table(log_db_path, "logs")
    return (
        logs[logs["levelname"].isin(ERROR_LEVELS)]
        if "levelname" in logs.columns
        else logs.iloc[0:0]
    )


@dataclass(frozen=True)
class HealthSummary:
    """What the navigation says about the engines, in as few facts as it
    can be said in."""

    down: tuple[str, ...]
    errors: int

    @property
    def alerts(self) -> int:
        return len(self.down) + self.errors


def summary(root: str) -> HealthSummary:
    """
    Everything under `root` that is worth interrupting a reader for: a
    component nothing has heard from, and a line an engine logged as an
    error.

    A sender that has never heartbeat at all is not down - there is
    nothing to have stopped - and reads as an engine still starting up
    where its own tiles are shown.
    """
    latest = heartbeats(root)
    now = time.time()
    down = (
        tuple(
            f"{row.engine_label} · {row.sender}"
            for row in latest.itertuples()
            if is_down(now - row.timestamp)
        )
        if not latest.empty
        else ()
    )
    return HealthSummary(down=down, errors=_error_count(root))


@st.cache_data(ttl=SCAN_SECONDS, show_spinner=False)
def _error_count(root: str) -> int:
    return sum(
        count_matching(engine.log_path, "logs", "levelname", ERROR_LEVELS)
        for engine in engine_databases(root)
    )
