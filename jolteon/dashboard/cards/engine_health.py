"""Every engine's components, and how recently each one was heard from."""

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.heartbeats import recent_heartbeats
from jolteon.dashboard.data.sqlite import as_datetime
from jolteon.dashboard.read_models.heartbeat_history import history
from jolteon.dashboard.services.health import heartbeats, is_down
from jolteon.dashboard.ui.cards import card_grid
from jolteon.dashboard.ui.empty_states import empty_state, warn_if_no_engines
from jolteon.dashboard.ui.primitives import BadgeColor, slug
from jolteon.engine.core.health_monitor.heartbeat import HeartbeatLevel
from jolteon.engine.core.health_monitor.parameters import (
    HeartbeatParameters,
)

HEARTBEAT_BADGES: dict[int, tuple[str, BadgeColor]] = {
    HeartbeatLevel.NORMAL.value: ("NORMAL", "green"),
    HeartbeatLevel.WARN.value: ("WARN", "yellow"),
    HeartbeatLevel.ERROR.value: ("ERROR", "orange"),
    HeartbeatLevel.CRITICAL.value: ("CRITICAL", "red"),
}

UNKNOWN_BADGE: tuple[str, BadgeColor] = ("UNKNOWN", "gray")

DOWN_BADGE: tuple[str, BadgeColor] = ("DOWN", "red")

# How often a component sends a heartbeat, so an interval it sent none
# in is an interval it missed.
HEARTBEAT_INTERVAL_SECONDS = HeartbeatParameters().interval_in_seconds

# How many intervals of history to show behind a component's state:
# about five minutes at the default interval, long enough to tell a
# component that has been flapping from one that has just gone quiet.
HISTORY_BUCKETS = 32

_HISTORY_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "heartbeat_history.css"
).read_text()


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
        columns=4,
        min_width=200,
        key_fn=lambda row: _tile_key(symbol, row.sender),
    ):
        label, color = _status(row)
        st.markdown(f"**{row.sender}**")
        st.badge(label, color=color)
        parts = [row.message] if row.message else []
        if is_down(row.quiet_for):
            parts.append(f"No heartbeat for {_describe_age(row.quiet_for)}")
        parts.append(f"Last seen {row.last_seen:%H:%M:%S} local time")
        st.caption(" · ".join(parts))
        _history_bars(symbol, row)


def heartbeat_history_html(reported: list[bool], *, down: bool) -> str:
    """
    Returns: One bar per interval, oldest first: filled where the sender
    heartbeat in it, hollow where it did not, and in the negative colour
    for every interval a component now down has missed since its last
    heartbeat - the whole row, where it has been quiet longer than the
    row reaches back.

    Spans rather than the prototype's SVG rects: `st.html` sanitises
    with DOMPurify's "html" profile, which strips `<svg>` outright but
    leaves a styled span alone.
    """
    last_seen = max((i for i, seen in enumerate(reported) if seen), default=-1)
    kinds = []
    for i, seen in enumerate(reported):
        if seen:
            kinds.append("seen")
        elif down and i > last_seen:
            kinds.append("down")
        else:
            kinds.append("missed")
    bars = "".join(
        f'<span class="jolteon-beat jolteon-beat-{kind}"></span>'
        for kind in kinds
    )
    span = _describe_age(len(reported) * HEARTBEAT_INTERVAL_SECONDS)
    label = (
        f"Heartbeat history, last {span}: "
        f"{sum(reported)} of {len(reported)} intervals reported"
    )
    return (
        f'<div class="jolteon-beats" role="img" aria-label="{label}">'
        f"{bars}</div>"
    )


def _recording(engine_key: str) -> str:
    """The recording of the engine keyed `engine_key` - or no path at
    all, which reads as an empty recording, should the engine have gone
    from disk since the scan the tiles were drawn from."""
    return next(
        (
            engine.path
            for engine in engine_databases(st.session_state.root)
            if engine.key == engine_key
        ),
        "",
    )


def _history_bars(engine_key: str, row) -> None:
    """The sender's last few minutes of heartbeats, under its state."""
    now = time.time()
    beats = recent_heartbeats(
        _recording(engine_key),
        since_seconds=HISTORY_BUCKETS * HEARTBEAT_INTERVAL_SECONDS,
        now=now,
    )
    reported = history(
        beats,
        row.sender,
        interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
        buckets=HISTORY_BUCKETS,
        now=now,
    )
    st.html(
        f"<style>{_HISTORY_CSS}</style>"
        + heartbeat_history_html(reported, down=is_down(row.quiet_for))
    )


def render() -> None:
    if not warn_if_no_engines(st.session_state.root):
        return
    engines = engine_databases(st.session_state.root)

    latest = heartbeats(st.session_state.root)
    for engine in engines:
        # An engine that has only just started has nothing to show yet,
        # and saying so is what keeps it from looking like one that never
        # started at all.
        if len(engines) > 1:
            st.markdown(f"**{engine.label}**")
        found = (
            latest[latest["engine_key"] == engine.key]
            if not latest.empty
            else latest
        )
        if found.empty:
            empty_state("No heartbeats recorded yet.")
        else:
            _tiles(engine.key, found)
