"""The navigation's own alert: a dot on Health while an engine is unwell.

The navigation is built by the entrypoint and a page refreshing itself
never re-runs that, so the dot is kept in step from a fragment of its
own.
"""

from pathlib import Path

import streamlit as st

from jolteon.dashboard.services.health import HealthSummary, summary

NAV_TITLE = "Health"
NAV_ICON = ":material/monitor_heart:"

_ALERT_DOT_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "nav_alert_dot.css"
).read_text()


def nav_alert_rule(current: HealthSummary) -> str:
    """
    Returns: The style that marks the Health navigation item as wanting
    attention, empty of rules when there is none to want.

    A count in the title read as part of the page's name and moved the
    item's width every time an error was logged, and an icon that changed
    shape changed what the item looked like it was for, so what there is
    to look at is said with a dot beside a name that stays put.
    """
    return f"<style>{_ALERT_DOT_CSS if current.alerts else ''}</style>"


_NAV_ALERTING = "_whether_the_nav_drew_an_alert"


def nav_drawn(current: HealthSummary) -> None:
    st.session_state[_NAV_ALERTING] = bool(current.alerts)


def redraw_nav_if_stale(root: str) -> None:
    """
    Asks for a full rerun when what the navigation shows has gone out of
    date.

    This is a deliberate whole-app rerun, and it fires
    only on the change itself - an engine's first error, or its last one
    ageing out - never on a refresh that found nothing new.

    Navigation is built by the entrypoint, and a fragment rerunning on
    its own timer never re-runs that, so a page refreshing itself would
    otherwise leave the Health item without the dot it should be
    wearing, or wearing one it should have dropped.

    What the navigation shows is a dot or no dot, so whether there is
    anything to alert about is all that is compared. Comparing the whole
    summary instead tore down and rebuilt the entire page every time an
    engine logged an error - once every few seconds on a busy one - to
    redraw a dot that was already there.

    What was found is recorded as drawn before the rerun rather than
    after it: the entrypoint records the same answer again a moment
    later, and recording it here is what makes this one rerun per change
    instead of one per refresh.
    """
    alerting = bool(summary(root).alerts)
    drawn = st.session_state.get(_NAV_ALERTING)
    st.session_state[_NAV_ALERTING] = alerting
    if drawn is not None and drawn != alerting:
        st.rerun(scope="app")


def _check_nav() -> None:
    redraw_nav_if_stale(st.session_state.root)


def watch_nav(run_every: float | None) -> None:
    """
    Keeps the navigation's alert dot in step with the engines, on a timer
    of its own.

    Its own fragment rather than a card's: what the dot reports on is
    every engine at once, so no one card on the page owns it, and a card
    that the reader has hidden would take the dot's timer down with it.
    """
    st.fragment(_check_nav, run_every=run_every)()
