import re
from datetime import datetime

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
    latest = latest.sort_values("sender")

    tile_keys: list[tuple[str, BadgeColor]] = []
    for row in card_grid(
        list(latest.itertuples()),
        columns=3,
        key_fn=lambda row: _tile_key(row.sender),
    ):
        label, color, icon = HEARTBEAT_BADGES.get(
            row.level, ("UNKNOWN", "gray", ":material/help:")
        )
        tile_keys.append((_tile_key(row.sender), color))
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{row.sender}**")
            st.badge(label, color=color, icon=icon)
        last_seen = f"Last seen {row.last_seen:%H:%M:%S} local time"
        caption = f"{row.message} · {last_seen}" if row.message else last_seen
        st.caption(caption)

    rules = "\n".join(
        f".st-key-{key} {{ background-color: "
        f"{TILE_BACKGROUNDS.get(color, TILE_BACKGROUNDS['gray'])}; }}"
        for key, color in tile_keys
    )
    st.html(f"<style>{rules}</style>")
