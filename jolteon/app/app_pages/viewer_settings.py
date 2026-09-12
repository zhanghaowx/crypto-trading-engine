from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

import streamlit as st

from jolteon.app.components import card_surface_rule

# Every one of these is read by the Live page, which does not render the
# widget that holds it. Without session persistence the value is dropped
# as soon as this page stops being rendered, and the Live page then fails
# reaching for a setting that was there a moment ago.
_PERSIST: Literal["session"] = "session"

_CARD_KEY = "viewer-settings-card"

# A slider left to stretch runs the whole width of its column, which reads
# as a different kind of control than the toggle sitting next to it.
_CONTROL_WIDTH = 320

_ROWS_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "settings_rows.css"
).read_text()


def _rows_rule() -> str:
    return f"<style>{_ROWS_CSS % {'card': f'.st-key-{_CARD_KEY}'}}</style>"


@contextmanager
def _setting(label: str, help_text: str) -> Iterator[None]:
    """A settings row, laid out so that controls of different natural
    widths (a toggle, a slider) still line up down the card."""
    described, control = st.columns([1, 1], vertical_alignment="center")
    described.markdown(label, help=help_text)
    with control:
        yield


def render() -> None:
    st.html(card_surface_rule([_CARD_KEY]) + _rows_rule())
    with st.container(border=True, key=_CARD_KEY):
        with _setting(
            "Auto-refresh", "Reload the Live page on the interval below."
        ):
            st.toggle(
                "Auto-refresh",
                key="auto_refresh",
                label_visibility="collapsed",
                persist_state=_PERSIST,
            )
        st.divider()
        with _setting(
            "Refresh interval (seconds)",
            "How long the Live page waits before reloading.",
        ):
            st.slider(
                "Refresh interval (seconds)",
                1,
                30,
                key="refresh_seconds",
                width=_CONTROL_WIDTH,
                label_visibility="collapsed",
                persist_state=_PERSIST,
            )
        st.divider()
        with _setting(
            "Chart window (minutes)",
            "How much history Market Data's price chart and Risk "
            "Limits' sparklines show.",
        ):
            st.slider(
                "Chart window (minutes)",
                1,
                120,
                key="chart_window_minutes",
                width=_CONTROL_WIDTH,
                label_visibility="collapsed",
                persist_state=_PERSIST,
            )

    if not Path(st.session_state.db_path).exists():
        st.warning(f"No database found at `{st.session_state.db_path}` yet.")

    if not Path(st.session_state.log_db_path).exists():
        st.warning(
            f"No log database found at `{st.session_state.log_db_path}` yet."
        )
