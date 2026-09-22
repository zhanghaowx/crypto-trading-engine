import streamlit as st

from jolteon.dashboard.cards import engine_health, logs
from jolteon.dashboard.services.health import summary
from jolteon.dashboard.settings import refresh_interval
from jolteon.dashboard.ui.cards import Accent, Card, cards_rule, render_cards
from jolteon.dashboard.ui.navigation import watch_nav


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
