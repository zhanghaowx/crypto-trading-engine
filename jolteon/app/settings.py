"""CLI args and per-viewer session state for the dashboard."""

import argparse

import streamlit as st

from jolteon.app.data import engine_databases

# Whether db_path is still whichever engine was found first, rather than
# one the reader chose.
_AUTO = "_engine_chosen_automatically"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # Matches the engine's own naming, which puts the symbol it trades in
    # the file name. A pattern rather than one path because one engine
    # trades one symbol: watching two symbols means reading two files.
    parser.add_argument("--db", default="/tmp/jolteon-*.sqlite")
    # Left unset, each engine's log database is found next to its
    # recording; give this to pin every page to one log file instead.
    parser.add_argument("--log-db", default="")
    # Matches the engine's own --params-db default. The dashboard is the
    # only writer of this file; the engine only ever reads it.
    parser.add_argument("--params-db", default="/tmp/jolteon.params.sqlite")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def init_settings() -> None:
    args = parse_args()
    st.session_state.setdefault("db_glob", args.db)
    st.session_state.setdefault("log_db_override", args.log_db)

    # Re-resolved every run until someone picks an engine, so a dashboard
    # opened before the engine starts finds it on a later refresh rather
    # than staying pinned to a file that did not exist at the time.
    if "db_path" not in st.session_state or st.session_state.get(_AUTO):
        engines = engine_databases(st.session_state.db_glob)
        first = engines[0] if engines else None
        st.session_state.db_path = (
            first.path if first else st.session_state.db_glob
        )
        st.session_state.log_db_path = args.log_db or (
            first.log_path if first else ""
        )
        st.session_state[_AUTO] = True
    st.session_state.setdefault("params_db_path", args.params_db)
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_seconds", 5)
    # Shared by Market Data's price chart and Risk Limits' sparklines, so
    # the two pages always show the same stretch of history.
    st.session_state.setdefault("chart_window_minutes", 15)


def use_engine(engine) -> None:
    """
    Points every page that reads one engine's recording at this one.

    Each engine records to its own file, so choosing a symbol is choosing
    a database, and the log database that goes with it.
    """
    st.session_state.db_path = engine.path
    st.session_state.log_db_path = (
        st.session_state.log_db_override or engine.log_path
    )
    st.session_state[_AUTO] = False
