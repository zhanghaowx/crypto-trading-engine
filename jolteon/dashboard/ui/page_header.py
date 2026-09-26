"""The context bar a page opens with: what everything under it is
scoped to. The navigation names the page; no page carries a heading of
its own."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import streamlit as st

from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.state import AUTO_REFRESH, refresh_interval
from jolteon.dashboard.ui.cards import surface_rule
from jolteon.dashboard.ui.engine_selection import run_mode_badges, run_status
from jolteon.dashboard.ui.primitives import BadgeColor

_SCOPE_BAR_KEY = "run-scope-bar"
_SCOPE_END_KEY = "run-scope-end"
_FEED_STATE = "live-feed-state"

_STATIC = Path(__file__).resolve().parents[1] / "static"
_CONTEXT_BAR_CSS = (_STATIC / "context_bar.css").read_text()

# A run's status carries its own weight, the same way a heartbeat's
# does: running is the quiet, expected case, and only a run that ended
# abnormally is worth a warmer color.
_STATUS_COLORS: dict[str, BadgeColor] = {
    "running": "green",
    "stopped": "gray",
    "interrupted": "orange",
}


@contextmanager
def scope_bar() -> Iterator[None]:
    """A bordered bar for whatever names the scope of the content below
    it: the engine, the run, the symbol a setting applies to."""
    st.html(
        surface_rule([_SCOPE_BAR_KEY]) + f"<style>{_CONTEXT_BAR_CSS}</style>"
    )
    with st.container(border=True, key=_SCOPE_BAR_KEY):
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small"
        ):
            yield


@contextmanager
def scope_bar_end() -> Iterator[None]:
    """The far end of a scope bar: what is said about the scope, apart
    from what chooses it."""
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        gap="small",
        key=_SCOPE_END_KEY,
        width="content",
    ):
        yield


@contextmanager
def context_bar(
    run: RecordedEngineRun | None, *, live: bool = False
) -> Iterator[None]:
    """
    Which run everything below is scoped to, drawn the same way wherever
    a page needs to say it.

    The page's own pickers go inside the block. The run's status and its
    two modes follow them as badges, and the bar ends with the run's
    identity - and, on a page reading a live feed, with whether the page
    is still following that feed.
    """
    with scope_bar():
        yield
        if run is not None:
            st.badge(
                run_status(run),
                color=_STATUS_COLORS.get(run.status, "gray"),
            )
            for label, color in run_mode_badges(run):
                st.badge(label, color=color)
        if live or run is not None:
            with scope_bar_end():
                if live:
                    _live_state()
                if run is not None:
                    short_id = run.run_id.rsplit("-", 1)[-1]
                    st.caption(
                        f"Run `{short_id}` · started "
                        f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC",
                        width="content",
                    )


def _apply_feed_state() -> None:
    st.session_state[AUTO_REFRESH] = st.session_state[_FEED_STATE] == "Live"


def _live_state() -> None:
    """
    A live feed's resting state: a pulse while the page follows the feed,
    drained while it is paused, and the control that switches between
    the two. Cards here refresh on their own timers, so what is said is
    how often they redraw - never that everything on the page just did.
    """
    interval = refresh_interval()
    paused = interval is None
    classes = "jolteon-live-dot paused" if paused else "jolteon-live-dot"
    st.html(f'<span class="{classes}"></span>', width="content")
    st.caption(
        "Paused" if paused else f"Refreshing every {interval:g} s",
        width="content",
    )
    # Seeded from the reader's setting on every run rather than left to
    # the widget's own memory, so refreshing switched off on the settings
    # page reads as paused here too.
    st.session_state[_FEED_STATE] = "Paused" if paused else "Live"
    st.segmented_control(
        "Feed",
        ["Live", "Paused"],
        key=_FEED_STATE,
        required=True,
        on_change=_apply_feed_state,
        label_visibility="collapsed",
    )
