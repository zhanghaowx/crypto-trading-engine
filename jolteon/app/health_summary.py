"""
Health as it stands across every engine under the root.

One engine trades one symbol and records into a directory of its own, so
a component's health is only ever half a fact: the other half is which
engine's it was. Everything here reads every engine and carries that
symbol along.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.app.data import (
    SCAN_SECONDS,
    EngineDatabase,
    count_matching,
    engine_databases,
    read_latest_per_group,
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


NAV_TITLE = "Health"
NAV_ICON = ":material/monitor_heart:"

_ALERT_DOT_CSS = (
    Path(__file__).resolve().parent / "static" / "nav_alert_dot.css"
).read_text()


def nav_alert_rule(current: HealthSummary) -> str:
    """
    Returns: The style that marks the Health navigation item as wanting
    attention, empty of rules when there is none to want.

    A count in the title read as part of the page's name and moved the
    item's width every time an error was logged, and an icon that changed
    shape changed what the item looked like it was for, so what there is
    to look at is said with a dot beside a name that stays put.
    """
    return f"<style>{_ALERT_DOT_CSS if current.alerts else ''}</style>"


_NAV_ALERTING = "_whether_the_nav_drew_an_alert"


def nav_drawn(current: HealthSummary) -> None:
    st.session_state[_NAV_ALERTING] = bool(current.alerts)


def redraw_nav_if_stale(root: str) -> None:
    """
    Asks for a full rerun when what the navigation shows has gone out of
    date.

    Navigation is built by the entrypoint, and a fragment rerunning on
    its own timer never re-runs that, so a page refreshing itself would
    otherwise leave the Health item without the dot it should be
    wearing, or wearing one it should have dropped.

    What the navigation shows is a dot or no dot, so whether there is
    anything to alert about is all that is compared. Comparing the whole
    summary instead tore down and rebuilt the entire page every time an
    engine logged an error - once every few seconds on a busy one - to
    redraw a dot that was already there.

    What was found is recorded as drawn before the rerun rather than
    after it: the entrypoint records the same answer again a moment
    later, and recording it here is what makes this one rerun per change
    instead of one per refresh.
    """
    alerting = bool(summary(root).alerts)
    drawn = st.session_state.get(_NAV_ALERTING)
    st.session_state[_NAV_ALERTING] = alerting
    if drawn is not None and drawn != alerting:
        st.rerun(scope="app")
