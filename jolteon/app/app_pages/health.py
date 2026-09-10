import re
from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, warn_if_no_db
from jolteon.app.data import as_datetime, read_latest_per_group
from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel

HEARTBEAT_BADGES: dict[int, tuple[str, BadgeColor, str]] = {
    HeartbeatLevel.NORMAL.value: (
        "NORMAL",
        "green",
        ":material/check_circle:",
    ),
    HeartbeatLevel.WARN.value: ("WARN", "yellow", ":material/warning:"),
    HeartbeatLevel.ERROR.value: ("ERROR", "orange", ":material/error:"),
    HeartbeatLevel.CRITICAL.value: ("CRITICAL", "red", ":material/dangerous:"),
}

UNKNOWN_BADGE: tuple[str, BadgeColor, str] = (
    "UNKNOWN",
    "gray",
    ":material/help:",
)

# A process that dies never reports its own death - its last heartbeat row
# just stops moving, often a cheerful NORMAL one - so silence is the only
# signal the dashboard has that a background component is gone.
#
# Live components heartbeat every 10s (see the `Heartbeater` subclasses under
# jolteon/market_data and jolteon/execution), and SignalRecorder writes each
# heartbeat out as it arrives, so a healthy sender looks at most one heartbeat
# cycle stale from here plus this page's own refresh interval. The timeout
# sits past two of those cycles; anything tighter would flag a running engine
# as down on nearly every refresh.
HEARTBEAT_TIMEOUT_SECONDS = 30

DOWN_BADGE: tuple[str, BadgeColor, str] = (
    "DOWN",
    "red",
    ":material/heart_broken:",
)


def _is_down(seconds_since_seen: float) -> bool:
    """Whether a sender has gone quiet for long enough to call it dead."""
    return seconds_since_seen > HEARTBEAT_TIMEOUT_SECONDS


def _describe_age(seconds: float) -> str:
    """How long a sender has been silent, in plain words."""
    for unit, size in (("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = round(seconds / size)
            return f"{count} {unit}{'s' if count != 1 else ''}"
    return f"{round(seconds)} seconds"


def _tile_key(sender: str) -> str:
    return "health-tile-" + re.sub(r"[^a-z0-9]+", "-", sender.lower()).strip(
        "-"
    )


def render() -> None:
    if not warn_if_no_db():
        return

    latest = read_latest_per_group(
        st.session_state.db_path, "heartbeat", "sender"
    )
    if latest.empty:
        st.info("No heartbeats recorded yet.")
        return

    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    latest["last_seen"] = as_datetime(latest["timestamp"]).dt.tz_convert(
        local_tz
    )
    latest["quiet_for"] = (
        pd.Timestamp.now(tz=local_tz) - latest["last_seen"]
    ).dt.total_seconds()
    latest = latest.sort_values("sender")
    rows = list(latest.itertuples())

    statuses: dict[str, tuple[str, BadgeColor, str]] = {
        row.sender: (
            DOWN_BADGE
            if _is_down(row.quiet_for)
            else HEARTBEAT_BADGES.get(row.level, UNKNOWN_BADGE)
        )
        for row in rows
    }

    for row in card_grid(
        rows, columns=3, key_fn=lambda row: _tile_key(row.sender)
    ):
        down = _is_down(row.quiet_for)
        label, color, icon = statuses[row.sender]
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{row.sender}**")
            st.badge(label, color=color, icon=icon)
        parts = [row.message] if row.message else []
        if down:
            parts.append(f"No heartbeat for {_describe_age(row.quiet_for)}")
        parts.append(f"Last seen {row.last_seen:%H:%M:%S} local time")
        st.caption(" · ".join(parts))
