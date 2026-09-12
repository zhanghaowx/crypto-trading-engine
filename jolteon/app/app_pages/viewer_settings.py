from pathlib import Path

import streamlit as st


def render() -> None:
    st.caption(
        "Settings for this dashboard viewer only — they do not "
        "affect the trading engine itself."
    )

    st.text_input("Database path", key="db_path")
    st.text_input("Log database path", key="log_db_path")
    st.text_input(
        "Parameter database path",
        key="params_db_path",
        help="Where the Engine tab pushes parameter changes for the "
        "engine to pick up.",
    )
    st.checkbox("Auto-refresh", key="auto_refresh")
    st.slider("Refresh every (s)", 1, 30, key="refresh_seconds")
    st.slider(
        "Chart window (minutes)",
        1,
        120,
        key="chart_window_minutes",
        help="How much history Market Data's price chart and Risk "
        "Limits' sparklines show.",
    )

    if not Path(st.session_state.db_path).exists():
        st.warning(f"No database found at `{st.session_state.db_path}` yet.")
    else:
        st.success(f"Reading from `{st.session_state.db_path}`.")

    if not Path(st.session_state.log_db_path).exists():
        st.warning(
            f"No log database found at `{st.session_state.log_db_path}` yet."
        )
    else:
        st.success(f"Reading logs from `{st.session_state.log_db_path}`.")
