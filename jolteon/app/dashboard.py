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
from pathlib import Path
from typing import Callable

import streamlit as st

from jolteon.app.app_pages import (
    health,
    logs,
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
# grey canvas, and the page would read as one continuous sheet.
def _section_key(title: str) -> str:
    return "card-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _section(title: str, icon: str, render_fn: Callable[[], None]) -> None:
    with st.container(border=True, key=_section_key(title)):
        st.subheader(title, icon=icon)
        render_fn()


def _render_sections(
    sections: list[tuple[str, str, Callable[[], None]]],
) -> None:
    for title, icon, render_fn in sections:
        _section(title, icon, render_fn)


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
        ("Market Data", ":material/show_chart:", market_data.render),
        ("Risk Limits", ":material/earthquake:", risk_limits.render),
        ("Orders & PnL", ":material/currency_bitcoin:", orders_pnl.render),
        ("Errors", ":material/error:", logs.render),
    ]

    # Emitted before any card renders, not after: Streamlit streams
    # elements to the browser as the script runs rather than painting the
    # whole page at once, so a card's own container can reach the DOM
    # several beats before the rule painting it white would - showing the
    # grey canvas underneath for a moment before it snaps to white. Cards
    # are keyed off the (static) titles above, so this needs nothing the
    # sections loop itself produces.
    selector = ", ".join(
        f".st-key-{_section_key(title)}" for title, *_ in sections
    )
    st.html(
        f"<style>"
        f"html {{ interpolate-size: allow-keywords; }}"
        f"{selector} {{ background-color: {CARD_BACKGROUND};"
        f" box-shadow: {CARD_SHADOW};"
        # `interpolate-size` (Chromium) is what lets a height transition
        # animate to/from `auto` at all; elsewhere this is simply a no-op
        # and a card's height still changes, just without the animation.
        f" transition: height 300ms ease, box-shadow 300ms ease; }}"
        f"</style>"
    )

    # `run_every` reruns just this fragment on a timer without blocking the
    # session - the previous `time.sleep` + `st.rerun()` loop did block it,
    # which let a periodic refresh race with a widget interaction inside it
    # (e.g. paging through Recent fills): the two reruns' element streams
    # could interleave and leave stale rows behind. Re-applying the
    # decorator every run picks up live changes to the auto-refresh setting.
    refresh_seconds = (
        st.session_state.refresh_seconds
        if st.session_state.auto_refresh
        else None
    )
    st.fragment(_render_sections, run_every=refresh_seconds)(sections)


main()
