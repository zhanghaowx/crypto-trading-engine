import re
from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, warn_if_no_db
from jolteon.app.data import as_datetime, read_table
from jolteon.core.health_monitor.heartbeat import HeartbeatLevel

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
# jolteon/market_data and jolteon/execution) and SignalRecorder only flushes
# to SQLite every 5s (`enable_auto_save` in jolteon/app/kraken.py), so even a
# perfectly healthy sender routinely looks ~15s stale from here. The timeout
# sits past two of those cycles; anything tighter would flag a running engine
# as down on nearly every refresh.
HEARTBEAT_TIMEOUT_SECONDS = 30

DOWN_BADGE: tuple[str, BadgeColor, str] = (
    "DOWN",
    "red",
    ":material/heart_broken:",
)

# Light tints of the theme's semantic colors (config.toml), used to color a
# whole health tile by status - there's no native `st.container` background
# option, so this is applied as scoped CSS keyed to each tile's container.
TILE_BACKGROUNDS: dict[BadgeColor, str] = {
    "green": "rgba(78, 159, 31, 0.16)",
    "yellow": "rgba(232, 185, 60, 0.20)",
    "orange": "rgba(232, 135, 60, 0.20)",
    "red": "rgba(226, 87, 76, 0.16)",
    "gray": "rgba(138, 143, 124, 0.14)",
}


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

    heartbeats = read_table(st.session_state.db_path, "heartbeat")
    if heartbeats.empty:
        st.info("No heartbeats recorded yet.")
        return

    latest = (
        heartbeats.sort_values("timestamp").groupby("sender").tail(1).copy()
    )
    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    latest["last_seen"] = as_datetime(latest["timestamp"]).dt.tz_convert(
        local_tz
    )
    latest["quiet_for"] = (
        pd.Timestamp.now(tz=local_tz) - latest["last_seen"]
    ).dt.total_seconds()
    latest = latest.sort_values("sender")

    tile_keys: list[tuple[str, BadgeColor]] = []
    for row in card_grid(
        list(latest.itertuples()),
        columns=3,
        key_fn=lambda row: _tile_key(row.sender),
    ):
        down = _is_down(row.quiet_for)
        label, color, icon = (
            DOWN_BADGE
            if down
            else HEARTBEAT_BADGES.get(row.level, UNKNOWN_BADGE)
        )
        tile_keys.append((_tile_key(row.sender), color))
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{row.sender}**")
            st.badge(label, color=color, icon=icon)
        parts = [row.message] if row.message else []
        if down:
            parts.append(f"No heartbeat for {_describe_age(row.quiet_for)}")
        parts.append(f"Last seen {row.last_seen:%H:%M:%S} local time")
        st.caption(" · ".join(parts))

    rules = "\n".join(
        f".st-key-{key} {{ background-color: "
        f"{TILE_BACKGROUNDS.get(color, TILE_BACKGROUNDS['gray'])}; }}"
        for key, color in tile_keys
    )
    st.html(f"<style>{rules}</style>")
