import streamlit as st

from jolteon.app.app_pages import engine_health, logs
from jolteon.app.card import Accent, Card, cards_rule, render_cards
from jolteon.app.health_summary import summary, watch_nav
from jolteon.app.settings import refresh_interval


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

render_cards(cards)
watch_nav(refresh_interval())
