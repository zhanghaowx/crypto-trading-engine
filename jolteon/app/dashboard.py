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

import re
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
from jolteon.app.components import CARD_BACKGROUND, CARD_SHADOW
from jolteon.app.settings import init_settings

_LOGO_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "images" / "jolteon.png"
)


# Section cards are keyed so scoped CSS can style them (see `CARD_BACKGROUND`
# and `CARD_SHADOW`); without it they'd be flat and transparent against the
# sage canvas, and the page would read as one continuous sheet.
def _section_key(title: str) -> str:
    return "card-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _section(title: str, icon: str, render_fn: Callable[[], None]) -> None:
    with st.container(border=True, key=_section_key(title)):
        st.subheader(title, icon=icon)
        render_fn()


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    init_settings()
    st.logo(str(_LOGO_PATH), size="large")

    _, settings_col = st.columns([8, 1], vertical_alignment="center")
    with settings_col.popover(
        "Settings", icon=":material/settings:", width="stretch"
    ):
        parameters.render()

    sections: list[tuple[str, str, Callable[[], None]]] = [
        # Health leads: if a component has gone quiet, everything below it
        # is stale data and the reader needs to know that first.
        ("Health", ":material/monitor_heart:", health.render),
        ("Market Data", ":material/candlestick_chart:", market_data.render),
        ("Risk Limits", ":material/earthquake:", risk_limits.render),
        ("Orders & PnL", ":material/currency_bitcoin:", orders_pnl.render),
    ]
    for title, icon, render_fn in sections:
        _section(title, icon, render_fn)

    selector = ", ".join(
        f".st-key-{_section_key(title)}" for title, *_ in sections
    )
    st.html(
        f"<style>{selector} {{ background-color: {CARD_BACKGROUND};"
        f" box-shadow: {CARD_SHADOW}; }}</style>"
    )

    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_seconds)
        st.rerun()


main()
