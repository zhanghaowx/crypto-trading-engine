"""
Live Streamlit dashboard for the Jolteon trading engine.

This is a read-only viewer: it never talks to the running engine directly.
Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/app/dashboard.py -- --db /tmp/jolteon.sqlite

The engine records every signal as it happens (see
jolteon/core/sqlite_writer.py), and the database is in WAL mode, so these
reads never block the engine's writes and lag it only by this page's own
refresh interval.
"""

import time
from pathlib import Path
from typing import Callable

import streamlit as st

from jolteon.app.app_pages import (
    health,
    market_data,
    orders_pnl,
    parameters,
    risk_limits,
)
from jolteon.app.settings import init_settings

_LOGO_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "images" / "jolteon.png"
)


def _section(title: str, icon: str, render_fn: Callable[[], None]) -> None:
    with st.container(border=True):
        st.subheader(title, icon=icon)
        render_fn()


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    init_settings()
    st.logo(str(_LOGO_PATH), size="large")

    _, settings_col = st.columns([8, 1], vertical_alignment="center")
    with settings_col.popover(
        "Settings", icon=":material/settings:", use_container_width=True
    ):
        parameters.render()

    _section("Market Data", ":material/candlestick_chart:", market_data.render)
    _section("Risk Limits", ":material/earthquake:", risk_limits.render)
    _section(
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
    )
    _section("Health", ":material/monitor_heart:", health.render)

    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_seconds)
        st.rerun()


main()
