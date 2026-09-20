import streamlit as st

from jolteon.app.app_pages import engine_health, logs
from jolteon.app.card import Accent, Card, cards_rule, render_cards
from jolteon.app.health_summary import redraw_nav_if_stale, summary


def _down_accent() -> Accent:
    return "red" if summary(st.session_state.root).down else "green"


def _errors_accent() -> Accent:
    return "red" if summary(st.session_state.root).errors else None


cards = [
    Card(
        "health",
        "Health",
        ":material/monitor_heart:",
        engine_health.render,
        accent=_down_accent,
    ),
    Card(
        "errors",
        "Errors",
        ":material/error:",
        logs.render,
        accent=_errors_accent,
    ),
]

st.html(cards_rule(cards))

_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)


def _refresh(cards: list[Card]) -> None:
    render_cards(cards)
    redraw_nav_if_stale(st.session_state.root)


st.fragment(_refresh, run_every=_refresh_seconds)(cards)
