import re
from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, warn_if_no_db
from jolteon.app.data import as_datetime, read_latest_per_group
from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel

HEARTBEAT_BADGES: dict[int, tuple[str, BadgeColor]] = {
    HeartbeatLevel.NORMAL.value: ("NORMAL", "green"),
    HeartbeatLevel.WARN.value: ("WARN", "yellow"),
    HeartbeatLevel.ERROR.value: ("ERROR", "orange"),
    HeartbeatLevel.CRITICAL.value: ("CRITICAL", "red"),
}

UNKNOWN_BADGE: tuple[str, BadgeColor] = ("UNKNOWN", "gray")

_DOT_HEX: dict[BadgeColor, str] = {
    "green": "#16A34A",
    "yellow": "#E8B93C",
    "orange": "#E8873C",
    "red": "#DC2626",
    "gray": "#8A8D91",
}

_DOT_CSS = """
<style>
@media (prefers-reduced-motion: no-preference) {
  .jolteon-status-dot { animation: jolteon-glow 1.8s ease-in-out infinite; }
}
@keyframes jolteon-glow {
  0%, 100% { box-shadow: 0 0 0 0 currentColor; }
  50% { box-shadow: 0 0 6px 2px currentColor; }
}
.jolteon-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
"""


def _status_dot(color: BadgeColor) -> str:
    hex_color = _DOT_HEX.get(color, _DOT_HEX["gray"])
    style = f"background:{hex_color}; color:{hex_color}"
    return f'<span class="jolteon-status-dot" style="{style}"></span>'


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

DOWN_BADGE: tuple[str, BadgeColor] = ("DOWN", "red")


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

    statuses: dict[str, tuple[str, BadgeColor]] = {
        row.sender: (
            DOWN_BADGE
            if _is_down(row.quiet_for)
            else HEARTBEAT_BADGES.get(row.level, UNKNOWN_BADGE)
        )
        for row in rows
    }

    for row in card_grid(
        rows,
        key="health-tiles",
        columns=6,
        min_width=240,
        key_fn=lambda row: _tile_key(row.sender),
    ):
        down = _is_down(row.quiet_for)
        label, color = statuses[row.sender]
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{row.sender}**")
            with st.container(
                horizontal=True, vertical_alignment="center", gap=0
            ):
                st.html(_status_dot(color), width="content")
                st.badge(label, color=color)
        parts = [row.message] if row.message else []
        if down:
            parts.append(f"No heartbeat for {_describe_age(row.quiet_for)}")
        parts.append(f"Last seen {row.last_seen:%H:%M:%S} local time")
        st.caption(" · ".join(parts))

    st.html(_DOT_CSS)
