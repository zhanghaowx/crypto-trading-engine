"""The heading, purpose line and run scope every page opens with."""

import streamlit as st

from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.ui.engine_selection import run_mode, run_status


def page_heading(title: str, purpose: str) -> None:
    """A page's own title and a one-line statement of what it is for -
    drawn before any scope bar or content, the same way on every page."""
    st.title(title)
    st.caption(purpose)


def run_scope_caption(run: RecordedEngineRun | None) -> None:
    """Which run everything below is scoped to, worded the same way
    wherever a page needs to say it - and nothing at all before an
    engine has recorded one."""
    if run is None:
        return
    short_id = run.run_id.rsplit("-", 1)[-1]
    st.caption(
        f"Run `{short_id}` · started "
        f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC · {run_status(run)} · "
        f"{run_mode(run)}"
    )
