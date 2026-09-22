"""What a page says where the recording it reads is not there yet."""

import streamlit as st

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
