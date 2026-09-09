from pathlib import Path

import streamlit as st

def render() -> None:
    st.caption(
        "Settings for this dashboard viewer only — they do not "
        "affect the trading engine itself."
    )

    st.text_input("Database path", key="db_path")
    st.checkbox("Auto-refresh", key="auto_refresh")
    st.slider("Refresh every (s)", 1, 30, key="refresh_seconds")

    if not Path(st.session_state.db_path).exists():
        st.warning(f"No database found at `{st.session_state.db_path}` yet.")
    else:
        st.success(f"Reading from `{st.session_state.db_path}`.")
