import streamlit as st

from jolteon.app.app_pages import engine_health, logs
from jolteon.app.components import (
    Section,
    render_sections,
    section_surface_rule,
)
from jolteon.app.health_summary import redraw_nav_if_stale

sections: list[Section] = [
    ("Health", ":material/monitor_heart:", engine_health.render, None),
    ("Errors", ":material/error:", logs.render, None),
]

st.html(section_surface_rule(title for title, *_ in sections))

_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)


def _refresh(sections: list[Section]) -> None:
    render_sections(sections)
    redraw_nav_if_stale(st.session_state.root)


st.fragment(_refresh, run_every=_refresh_seconds)(sections)
