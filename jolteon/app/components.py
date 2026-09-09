"""Shared UI helpers used by more than one dashboard page."""

from pathlib import Path
from typing import Literal

import streamlit as st

BadgeColor = Literal[
    "red",
    "orange",
    "yellow",
    "blue",
    "green",
    "violet",
    "gray",
    "grey",
    "primary",
]


def card_grid(items, columns: int = 3, key_fn=None):
    """
    Lay `items` out as a responsive grid of bordered cards, up to `columns`
    per row. Yields each item with its own bordered container already
    open, so the caller just renders content into it - handy for pages
    (risk limits, health) where the number of cards grows over time.

    `key_fn`, if given, computes a stable container `key` from each item,
    letting the caller target individual cards with scoped CSS (e.g. via
    `.st-key-<key>`) - such as coloring a card by status.
    """
    items = list(items)
    if not items:
        return
    cols_per_row = min(columns, len(items))
    for start in range(0, len(items), cols_per_row):
        row_items = items[start : start + cols_per_row]
        row_cols = st.columns(cols_per_row)
        for col, item in zip(row_cols, row_items):
            key = key_fn(item) if key_fn else None
            with col, st.container(border=True, key=key):
                yield item


def warn_if_no_db() -> bool:
    """Returns whether the configured database exists yet."""
    db_path = st.session_state.db_path
    if Path(db_path).exists():
        return True
    st.warning(
        f"No database found at `{db_path}` yet. "
        f"Waiting for the engine to start recording... "
        f"(check the Parameters tab if this looks wrong)"
    )
    return False
