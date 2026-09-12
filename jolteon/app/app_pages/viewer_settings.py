from pathlib import Path
from typing import Literal

import streamlit as st

# Every one of these is read by the Live page, which does not render the
# widget that holds it. Without session persistence the value is dropped
# as soon as this page stops being rendered, and the Live page then fails
# reaching for a setting that was there a moment ago.
_PERSIST: Literal["session"] = "session"


def render() -> None:
    st.caption(
        "Settings for this dashboard viewer only — they do not "
        "affect the trading engine itself."
    )

    st.text_input("Database path", key="db_path", persist_state=_PERSIST)
    st.text_input(
        "Log database path", key="log_db_path", persist_state=_PERSIST
    )
    st.text_input(
        "Parameter database path",
        key="params_db_path",
        persist_state=_PERSIST,
        help="Where the Engine tab pushes parameter changes for the "
        "engine to pick up.",
    )
    st.checkbox("Auto-refresh", key="auto_refresh", persist_state=_PERSIST)
    st.slider(
        "Refresh every (s)",
        1,
        30,
        key="refresh_seconds",
        persist_state=_PERSIST,
    )
    st.slider(
        "Chart window (minutes)",
        1,
        120,
        key="chart_window_minutes",
        persist_state=_PERSIST,
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
