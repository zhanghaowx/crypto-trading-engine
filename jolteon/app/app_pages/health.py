import streamlit as st

from jolteon.app.app_pages import engine_health, logs
from jolteon.app.components import (
    Section,
    render_sections,
    section_surface_rule,
)

sections: list[Section] = [
    ("Health", ":material/monitor_heart:", engine_health.render, None),
    ("Errors", ":material/error:", logs.render, None),
]

st.html(section_surface_rule(title for title, *_ in sections))

_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)
st.fragment(render_sections, run_every=_refresh_seconds)(sections)
