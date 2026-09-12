import streamlit as st

from jolteon.app.app_pages import engine_parameters, viewer_settings

engine_tab, dashboard_tab = st.tabs(["Engine", "Dashboard"])

# Both tabs' content is built on every run, so without a fragment each of
# them reruns whenever a widget in the other one is touched - and editing
# one parameter rebuilds all of them. A fragment keeps a rerun to the tab
# the edit happened in.
with engine_tab:
    st.fragment(engine_parameters.render)()

with dashboard_tab:
    st.fragment(viewer_settings.render)()
