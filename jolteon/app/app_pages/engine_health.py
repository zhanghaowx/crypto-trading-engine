"""Every engine's components, and how recently each one was heard from."""

from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, slug
from jolteon.app.data import as_datetime, engine_databases
from jolteon.app.health_summary import heartbeats, is_down
from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel

HEARTBEAT_BADGES: dict[int, tuple[str, BadgeColor]] = {
    HeartbeatLevel.NORMAL.value: ("NORMAL", "green"),
    HeartbeatLevel.WARN.value: ("WARN", "yellow"),
    HeartbeatLevel.ERROR.value: ("ERROR", "orange"),
    HeartbeatLevel.CRITICAL.value: ("CRITICAL", "red"),
}

UNKNOWN_BADGE: tuple[str, BadgeColor] = ("UNKNOWN", "gray")

DOWN_BADGE: tuple[str, BadgeColor] = ("DOWN", "red")

_DOT_HEX: dict[BadgeColor, str] = {
    "green": "#16A34A",
    "yellow": "#E8B93C",
    "orange": "#E8873C",
    "red": "#DC2626",
    "gray": "#8A8D91",
}


def _status_dot(color: BadgeColor) -> str:
    hex_color = _DOT_HEX.get(color, _DOT_HEX["gray"])
    style = f"background:{hex_color}; color:{hex_color}"
    return f'<span class="jolteon-status-dot" style="{style}"></span>'


def _describe_age(seconds: float) -> str:
    """How long a sender has been silent, in plain words."""
    for unit, size in (("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = round(seconds / size)
            return f"{count} {unit}{'s' if count != 1 else ''}"
    return f"{round(seconds)} seconds"


def _tile_key(symbol: str, sender: str) -> str:
    # Senders are named for the job they do, so every engine has an `MD`
    # and a `MarketMaking`; without the symbol two engines' tiles would
    # share a key and the second would reuse the first's DOM node.
    return f"health-tile-{slug(symbol)}-{slug(sender)}"


def _local(latest: pd.DataFrame) -> pd.DataFrame:
    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    latest = latest.assign(
        last_seen=as_datetime(latest["timestamp"]).dt.tz_convert(local_tz)
    )
    return latest.assign(
        quiet_for=(
            pd.Timestamp.now(tz=local_tz) - latest["last_seen"]
        ).dt.total_seconds()
    ).sort_values("sender")


def _status(row) -> tuple[str, BadgeColor]:
    if is_down(row.quiet_for):
        return DOWN_BADGE
    return HEARTBEAT_BADGES.get(row.level, UNKNOWN_BADGE)


def _tiles(symbol: str, latest: pd.DataFrame) -> None:
    rows = list(_local(latest).itertuples())
    for row in card_grid(
        rows,
        key=f"health-tiles-{slug(symbol)}",
        columns=6,
        min_width=240,
        key_fn=lambda row: _tile_key(symbol, row.sender),
    ):
        label, color = _status(row)
        st.markdown(f"**{row.sender}**")
        with st.container(horizontal=True, vertical_alignment="center", gap=0):
            st.html(_status_dot(color), width="content")
            st.badge(label, color=color)
        parts = [row.message] if row.message else []
        if is_down(row.quiet_for):
            parts.append(f"No heartbeat for {_describe_age(row.quiet_for)}")
        parts.append(f"Last seen {row.last_seen:%H:%M:%S} local time")
        st.caption(" · ".join(parts))


def render() -> None:
    engines = engine_databases(st.session_state.root)
    if not engines:
        st.warning(
            f"No engine has recorded anything under "
            f"`{st.session_state.root}` yet."
        )
        return

    latest = heartbeats(st.session_state.root)
    for engine in engines:
        # An engine that has only just started has nothing to show yet,
        # and saying so is what keeps it from looking like one that never
        # started at all.
        if len(engines) > 1:
            st.markdown(f"**{engine.symbol}**")
        found = (
            latest[latest["symbol"] == engine.symbol]
            if not latest.empty
            else latest
        )
        if found.empty:
            st.info("No heartbeats recorded yet.")
        else:
            _tiles(engine.symbol, found)
