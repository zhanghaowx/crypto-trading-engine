"""The heading, purpose line and run scope every page opens with."""

import streamlit as st

from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.ui.cards import surface_rule
from jolteon.dashboard.ui.engine_selection import run_mode, run_status
from jolteon.dashboard.ui.primitives import BadgeColor

_SCOPE_BAR_KEY = "run-scope-bar"

# A run's status carries its own weight, the same way a heartbeat's
# does: running is the quiet, expected case, and only a run that ended
# abnormally is worth a warmer color.
_STATUS_COLORS: dict[str, BadgeColor] = {
    "running": "green",
    "stopped": "gray",
    "interrupted": "orange",
}


def page_heading(title: str, purpose: str) -> None:
    """A page's own title and a one-line statement of what it is for -
    drawn before any scope bar or content, the same way on every page."""
    st.title(title)
    st.caption(purpose)


def run_scope_caption(run: RecordedEngineRun | None) -> None:
    """Which run everything below is scoped to, drawn the same way
    wherever a page needs to say it - and nothing at all before an
    engine has recorded one."""
    if run is None:
        return
    short_id = run.run_id.rsplit("-", 1)[-1]
    st.html(surface_rule([_SCOPE_BAR_KEY]))
    with st.container(border=True, key=_SCOPE_BAR_KEY):
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small"
        ):
            st.badge(
                run_status(run),
                color=_STATUS_COLORS.get(run.status, "gray"),
            )
            st.badge(run_mode(run), color="blue")
            st.caption(
                f"Run `{short_id}` · started "
                f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC"
            )
