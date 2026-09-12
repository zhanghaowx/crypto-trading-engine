"""CLI args and per-viewer session state for the dashboard."""

import argparse

import streamlit as st


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/tmp/jolteon.sqlite")
    # Matches the engine's own default: logfile_name="/tmp/jolteon.log"
    # plus the ".sqlite" suffix setup_global_logger appends to it.
    parser.add_argument("--log-db", default="/tmp/jolteon.log.sqlite")
    # Matches the engine's own --params-db default. The dashboard is the
    # only writer of this file; the engine only ever reads it.
    parser.add_argument("--params-db", default="/tmp/jolteon.params.sqlite")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def init_settings() -> None:
    args = parse_args()
    st.session_state.setdefault("db_path", args.db)
    st.session_state.setdefault("log_db_path", args.log_db)
    st.session_state.setdefault("params_db_path", args.params_db)
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_seconds", 5)
    # Shared by Market Data's price chart and Risk Limits' sparklines, so
    # the two pages always show the same stretch of history.
    st.session_state.setdefault("chart_window_minutes", 15)
