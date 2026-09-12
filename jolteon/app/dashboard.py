"""
Live Streamlit dashboard for the Jolteon trading engine.

The Live page is a read-only viewer: it never talks to the running engine
directly. Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/app/dashboard.py -- --db /tmp/jolteon.sqlite

The engine records every signal as it happens (see
jolteon/core/sqlite_writer.py), and the database is in WAL mode, so these
reads never block the engine's writes and lag it only by this page's own
refresh interval.

The Parameters page is the one part that writes: it pushes into a database
of its own that the engine polls, so neither process ever writes the file
the other one owns.
"""

from pathlib import Path

import streamlit as st

from jolteon.app.settings import init_settings

_LOGO_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "images" / "jolteon.png"
)

_FOCUS_CSS = (
    Path(__file__).resolve().parent / "static" / "focus_visible.css"
).read_text()


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    init_settings()
    st.logo(str(_LOGO_PATH), size="medium")
    st.html(f"<style>{_FOCUS_CSS}</style>")

    st.navigation(
        [
            st.Page(
                "app_pages/live.py",
                title="Live",
                icon=":material/monitoring:",
                default=True,
            ),
            st.Page(
                "app_pages/parameters.py",
                title="Parameters",
                icon=":material/tune:",
            ),
        ],
        position="top",
    ).run()


main()
