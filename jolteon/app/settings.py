"""CLI args and per-viewer session state for the dashboard."""

import argparse

import streamlit as st

from jolteon import paths
from jolteon.app.data import EngineDatabase, engine_databases

# Which symbol's engine every page that reads one engine is reading.
# Named for the query parameter it is bound to, since the widget holding
# it puts it in the URL.
SYMBOL = "symbol"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # The engine's own default. Every symbol traded under it has a
    # directory there, which is how the symbols on offer are found.
    parser.add_argument("--root", default=paths.DEFAULT_ROOT)
    # Left unset, each engine's log database is found in that engine's own
    # directory; give this to pin every page to one log file instead.
    parser.add_argument("--log-db", default="")
    # Defaults to the one store at the root of --root, shared by every
    # symbol. The dashboard is the only writer of it; the engine reads.
    parser.add_argument("--params-db", default="")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def init_settings() -> None:
    args = parse_args()
    st.session_state.setdefault("root", args.root)

    # Resolved on every run rather than remembered: engines start and
    # stop while a dashboard is open, and a reader who picked one that
    # has since gone would otherwise be left reading a file that is no
    # longer there.
    engine = _chosen_engine(st.session_state.root)
    st.session_state.db_path = engine.path if engine else ""
    st.session_state.log_db_path = args.log_db or (
        engine.log_path if engine else ""
    )

    st.session_state.setdefault(
        "params_db_path",
        args.params_db or paths.parameter_store(st.session_state.root),
    )
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_seconds", 5)
    # Shared by Market Data's price chart and Risk Limits' sparklines, so
    # the two pages always show the same stretch of history.
    st.session_state.setdefault("chart_window_minutes", 15)


def _chosen_engine(root: str) -> EngineDatabase | None:
    """
    Returns: The engine whose symbol is selected, the first one found
    while nothing is, and nothing at all under a root no engine has run
    under yet.

    Session state carries the symbol from this run's click. The URL is
    what seeds the first run, where the picker has not registered its
    value yet - and the run after a page that does not draw the picker
    at all.
    """
    engines = engine_databases(root)
    chosen = st.session_state.get(SYMBOL) or st.query_params.get(SYMBOL)
    return next(
        (engine for engine in engines if engine.symbol == chosen),
        engines[0] if engines else None,
    )
