"""
Live Streamlit dashboard for the Jolteon trading engine.

The Live page is a read-only viewer: it never talks to the running engine
directly. Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/dashboard/main.py -- --root /tmp/jolteon

Every engine writes under a directory of that root named after the exchange
and symbol it trades, so the symbols this can show are the directories it
finds. Every run an engine makes is a recording of its own in there, named
by its run id; whether the run read a live feed or replayed a recording is
written into the recording, not its name. The Live page reads one
instrument's newest live-feed run at a time; the Health page reads every
instrument's, so an engine that has gone quiet is visible whichever symbol
is on screen.

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

from jolteon.dashboard.services.health import summary
from jolteon.dashboard.state import init_state
from jolteon.dashboard.ui.navigation import (
    NAV_TITLE,
    nav_alert_rule,
    nav_drawn,
)
from jolteon.dashboard.ui.primitives import badge_css
from jolteon.engine.core.sentry.reporting import configure

configure(
    exchange="all",
    symbol="all",
    mode="dashboard",
    component="dashboard",
)

_STATIC = Path(__file__).resolve().parent / "static"

_LOGO_PATH = _STATIC / "jolteon.png"

# The stylesheets every page shares, the tokens first: every later rule
# names one of them.
_SHARED_CSS = (
    "".join(
        (_STATIC / name).read_text()
        for name in (
            "tokens.css",
            "nav.css",
            "page_top_padding.css",
            "focus_visible.css",
            "metric.css",
            "segmented_control.css",
        )
    )
    + badge_css()
)


def main() -> None:
    st.set_page_config(page_title="Jolteon", layout="wide")
    init_state()
    st.logo(str(_LOGO_PATH), size="medium")
    st.html(f"<style>{_SHARED_CSS}</style>")

    health = summary(st.session_state.root)
    nav_drawn(health)
    st.html(nav_alert_rule(health))

    # The pages live under `screens`, not `pages`: Streamlit takes a folder
    # of that name beside the entrypoint for its legacy multipage layout,
    # and on a process's first request to any URL but the root runs that
    # page's file on its own - before this function has seeded the state
    # every page reads.
    st.navigation(
        [
            st.Page("screens/live.py", title="Live monitor", default=True),
            st.Page("screens/health.py", title=NAV_TITLE, url_path="health"),
            st.Page(
                "screens/parameters.py",
                title="Parameters",
                url_path="parameters",
            ),
            st.Page(
                "screens/post_trade.py",
                title="Post-trade",
                url_path="post-trade",
            ),
        ],
        position="top",
    ).run()


main()
