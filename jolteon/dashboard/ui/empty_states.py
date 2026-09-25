"""What a page says where the recording it reads is not there yet."""

import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.sqlite import database_exists


def warn_if_no_db(db_path: str | None = None) -> bool:
    """Returns whether `db_path` (the main database by default) exists."""
    db_path = db_path or st.session_state.db_path
    if database_exists(db_path):
        return True
    st.warning(
        f"No database found at `{db_path}` yet. "
        f"Waiting for the engine to start recording... "
        f"(check the Parameters page if this looks wrong)"
    )
    return False


def warn_if_no_engines(root: str) -> bool:
    """Returns whether any engine has recorded anything under `root` -
    Health and the error log both watch every engine at once rather
    than the one a reader picked, so both say the same thing while
    there isn't one yet."""
    if engine_databases(root):
        return True
    st.warning(f"No engine has recorded anything under `{root}` yet.")
    return False


def empty_state(message: str) -> None:
    """
    A state that is empty rather than wrong: nothing has happened yet,
    not that something failed. Drawn as a quiet line of text rather
    than an alert, so a normal "nothing to report" does not compete for
    attention with a genuine warning or error shown elsewhere.
    """
    st.caption(message)
