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

st.title("Health")
if not warn_if_no_db():
    st.stop()

heartbeats = read_table(st.session_state.db_path, "heartbeat")
if heartbeats.empty:
    st.info("No heartbeats recorded yet.")
    st.stop()

latest = heartbeats.sort_values("timestamp").groupby("sender").tail(1).copy()
latest["last_seen"] = as_datetime(latest["timestamp"])
latest = latest.sort_values("sender")

for row in card_grid(list(latest.itertuples()), columns=3):
    label, color, icon = HEARTBEAT_BADGES.get(
        row.level, ("UNKNOWN", "gray", ":material/help:")
    )
    st.markdown(f"**{row.sender}**")
    st.badge(label, color=color, icon=icon)
    if row.message:
        st.caption(row.message)
    st.caption(f"Last seen {row.last_seen:%H:%M:%S} UTC")
