"""
Live Streamlit dashboard for the Jolteon trading engine.

This is a read-only viewer: it never talks to the running engine directly.
Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/app/dashboard.py -- --db /tmp/jolteon.sqlite

Note: live runs only flush to the database periodically (see
`enable_auto_save` in jolteon/app/kraken.py), so the dashboard lags behind
the engine by roughly that interval.
"""

import time
from pathlib import Path

import streamlit as st

from jolteon.app.settings import init_settings
from jolteon.app.styles import SIDEBAR_CSS

_LOGO_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "images" / "jolteon.png"
)


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    init_settings()

    st.html(SIDEBAR_CSS)
    st.logo(str(_LOGO_PATH), size="large")

    pages = [
        st.Page(
            "app_pages/market_data.py",
            title="Market Data",
            icon=":material/candlestick_chart:",
            default=True,
        ),
        st.Page(
            "app_pages/risk_limits.py",
            title="Risk Limits",
            icon=":material/warning:",
        ),
        st.Page(
            "app_pages/orders_pnl.py",
            title="Orders & PnL",
            icon=":material/account_balance_wallet:",
        ),
        st.Page(
            "app_pages/health.py",
            title="Health",
            icon=":material/monitor_heart:",
        ),
        st.Page(
            "app_pages/parameters.py",
            title="Parameters",
            icon=":material/settings:",
        ),
    ]
    pg = st.navigation(pages)

    pg.run()

    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_seconds)
        st.rerun()


main()
