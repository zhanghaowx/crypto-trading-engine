"""CLI args and per-viewer session state for the dashboard."""

import argparse

import streamlit as st


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/tmp/jolteon.sqlite")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def init_settings() -> None:
    args = parse_args()
    st.session_state.setdefault("db_path", args.db)
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_seconds", 5)
