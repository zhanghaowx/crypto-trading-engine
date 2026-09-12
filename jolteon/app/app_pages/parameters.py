import streamlit as st

from jolteon.app.app_pages import engine_parameters, viewer_settings

engine_tab, dashboard_tab = st.tabs(["Engine", "Dashboard"])

with engine_tab:
    engine_parameters.render()

with dashboard_tab:
    viewer_settings.render()
