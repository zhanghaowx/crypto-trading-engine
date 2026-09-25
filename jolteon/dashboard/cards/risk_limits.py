import math
from pathlib import Path

import streamlit as st

from jolteon.dashboard.data.sqlite import read_table
from jolteon.dashboard.ui.cards import Accent, card_grid
from jolteon.dashboard.ui.empty_states import empty_state, warn_if_no_db
from jolteon.dashboard.ui.primitives import SEMANTIC_COLORS, BadgeColor

_BAR_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "risk_limit_bar.css"
).read_text()

# Utilisation thresholds shared by the badge and the bar's own ticks, so
# the marks along the track are the points the badge changes band at.
ELEVATED_THRESHOLD = 0.7
NEAR_LIMIT_THRESHOLD = 0.9


def _limit_title(name: str) -> str:
    """A limit's recorded name as a heading: they are recorded the way
    the engine names them, in snake case."""
    return name.replace("_", " ").title()


def risk_limit_badge(utilization: float) -> tuple[str, BadgeColor, str]:
    if utilization >= NEAR_LIMIT_THRESHOLD:
        return "Near Limit", "red", ":material/error:"
    if utilization >= ELEVATED_THRESHOLD:
        return "Elevated", "orange", ":material/warning:"
    return "OK", "green", ":material/check_circle:"


def accent() -> Accent:
    """The card's edge color: what the closest limit to being breached
    would badge itself as, so a limit under pressure is visible from the
    top of the page without opening the card. Comfortable usage carries
    no accent - the card only earns one once a limit is worth watching."""
    risk = read_table(st.session_state.db_path, "risk_limit_snapshot")
    if risk.empty:
        return None
    latest = risk.sort_values("timestamp").groupby(["name", "symbol"]).last()
    used = [
        min(abs(row.current) / row.maximum, 1.0) if row.maximum else 0.0
        for row in latest.itertuples()
    ]
    color = risk_limit_badge(max(used))[1]
    return None if color == "green" else color


def _fmt_bound(value: float) -> str:
    """
    A limit's bound or its measured value, short enough to read at a
    glance - a recorded measure carries far more decimals than anyone
    checking a limit against it needs.

    Three significant figures rather than two decimal places: a limit
    measured in coins runs to thousandths, and rounding 0.0056 to "0.01"
    made the bar beside it look wrong when it was the number that was.
    """
    if not value:
        return "0"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    decimals = max(0, 2 - math.floor(math.log10(abs(value))))
    return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")


def utilisation_bar(utilization: float, color: BadgeColor) -> str:
    """
    Returns: The limit's utilisation as a filled track, with a tick at
    each threshold the badge changes band at.

    A plain `<div>` rather than the inline SVG the semicircular gauge
    needed: `st.html` sanitises with DOMPurify's "html" profile, which
    strips `<svg>` outright but leaves a styled div alone.
    """
    width = min(max(utilization, 0.0), 1.0) * 100
    ticks = "".join(
        f'<div class="jolteon-limit-tick" style="left:{t:.0%}"></div>'
        for t in (ELEVATED_THRESHOLD, NEAR_LIMIT_THRESHOLD)
    )
    return (
        f'<div class="jolteon-limit-track">'
        f'<div class="jolteon-limit-fill" style="width:{width:.1f}%;'
        f'background:{SEMANTIC_COLORS[color]}"></div>{ticks}</div>'
    )


def render() -> None:
    if not warn_if_no_db():
        return

    risk = read_table(st.session_state.db_path, "risk_limit_snapshot")
    if risk.empty:
        empty_state(
            "No risk limit data recorded yet "
            "(no strategy is live, or nothing has flushed to disk yet)."
        )
        return

    st.html(f"<style>{_BAR_CSS}</style>")
    risk = risk.sort_values("timestamp")
    groups = list(risk.groupby(["name", "symbol"]))

    for (name, symbol), history in card_grid(groups, key="risk-limit-cards"):
        latest = history.iloc[-1]
        maximum = latest["maximum"]
        utilization = (
            min(abs(latest["current"]) / maximum, 1.0) if maximum else 0.0
        )
        label, color, icon = risk_limit_badge(utilization)

        st.markdown(f"**{_limit_title(name)}**")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(symbol, width="content")
            st.badge(label, color=color, icon=icon)
        st.html(utilisation_bar(utilization, color))
        st.caption(
            f"{_fmt_bound(abs(latest['current']))} of "
            f"{_fmt_bound(maximum)} used - {utilization:.0%}"
        )
