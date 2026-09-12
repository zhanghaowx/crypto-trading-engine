import re
from typing import Callable

import streamlit as st

from jolteon.app.app_pages import (
    fair_price_signals,
    health,
    logs,
    market_data,
    orders_pnl,
    risk_limits,
)
from jolteon.app.components import CARD_BACKGROUND, CARD_SHADOW

Section = tuple[
    str,
    str,
    Callable[[], None],
    Callable[[], None] | None,
    Callable[[], bool] | None,
]


# Section cards are keyed so scoped CSS can style them (see `CARD_BACKGROUND`
# and `CARD_SHADOW`); without it they'd be flat and transparent against the
# grey canvas, and the page would read as one continuous sheet.
def _section_key(title: str) -> str:
    return "card-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _section(
    title: str,
    icon: str,
    render_fn: Callable[[], None],
    actions: Callable[[], None] | None = None,
    visible: Callable[[], bool] | None = None,
) -> None:
    if visible is not None and not visible():
        return
    with st.container(border=True, key=_section_key(title)):
        if actions is None:
            st.subheader(title, icon=icon)
        else:
            # A section's own action sits on the title's row instead of
            # pushing the section's content down to make room for it.
            title_col, actions_col = st.columns(
                [8, 1], vertical_alignment="center"
            )
            with title_col:
                st.subheader(title, icon=icon)
            with actions_col:
                actions()
        render_fn()


def _render_sections(sections: list[Section]) -> None:
    for title, icon, render_fn, actions, visible in sections:
        _section(title, icon, render_fn, actions, visible)


sections: list[Section] = [
    # Health leads: if a component has gone quiet, everything below it
    # is stale data and the reader needs to know that first.
    ("Health", ":material/monitor_heart:", health.render, None, None),
    (
        "Market Data",
        ":material/show_chart:",
        market_data.render,
        None,
        None,
    ),
    (
        "Risk Limits",
        ":material/earthquake:",
        risk_limits.render,
        None,
        None,
    ),
    (
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
        orders_pnl.render_header_actions,
        None,
    ),
    (
        "Trade Quality",
        ":material/target:",
        orders_pnl.render_trade_quality,
        None,
        None,
    ),
    (
        "Fair Price Signals",
        ":material/insights:",
        fair_price_signals.render,
        None,
        None,
    ),
    (
        "Errors",
        ":material/error:",
        logs.render,
        None,
        logs.has_errors,
    ),
]

# Emitted before any card renders, not after: Streamlit streams
# elements to the browser as the script runs rather than painting the
# whole page at once, so a card's own container can reach the DOM
# several beats before the rule painting it white would - showing the
# grey canvas underneath for a moment before it snaps to white. Cards
# are keyed off the (static) titles above, so this needs nothing the
# sections loop itself produces.
_selector = ", ".join(
    f".st-key-{_section_key(title)}" for title, *_ in sections
)
st.html(
    f"<style>"
    f"html {{ interpolate-size: allow-keywords; }}"
    f"{_selector} {{ background-color: {CARD_BACKGROUND};"
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
_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)
st.fragment(_render_sections, run_every=_refresh_seconds)(sections)
