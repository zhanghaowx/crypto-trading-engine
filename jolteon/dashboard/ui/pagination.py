"""Paging through a recorded table that is too long to put on a page."""

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

_PAGINATION_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "pagination.css"
).read_text()


def _shift_page(state_key: str, delta: int, page_count: int) -> None:
    """Moves a `paginate` page by `delta`, clamped to the valid range.

    Run as a button's `on_click`, so it lands in `session_state` *before*
    the script reruns - the rerun's own top-to-bottom pass then sees the
    new page from the very first line, and disabled states, captions and
    the sliced page all agree. Computed by incrementing a local variable
    inline instead, whichever widget came first in the code would still
    show the *old* page on the one rerun a click actually happens on.
    """
    current = st.session_state.get(state_key, 0)
    st.session_state[state_key] = min(max(current + delta, 0), page_count - 1)


def _goto_page(state_key: str, page: int) -> None:
    st.session_state[state_key] = page


def _page_window(
    current: int, total: int, siblings: int = 1
) -> list[int | None]:
    """Page indices to show as buttons: first, last, `siblings` around
    `current`, with a `None` for each collapsed gap between them."""
    if total <= 2 * siblings + 5:
        return list(range(total))
    window = {0, total - 1, current}
    for delta in range(1, siblings + 1):
        window.add(current - delta)
        window.add(current + delta)
    ordered = sorted(p for p in window if 0 <= p < total)
    pages: list[int | None] = []
    previous: int | None = None
    for p in ordered:
        if previous is not None and p - previous > 1:
            pages.append(None)
        pages.append(p)
        previous = p
    return pages


def paginate(
    df: pd.DataFrame, *, key: str, page_size: int = 10
) -> tuple[pd.DataFrame, Callable[[], None]]:
    """
    The current page of `df` (already sorted, newest first), paired with a
    function that draws its Previous/Next controls - call that separately,
    whereever the controls should actually sit (typically below the rows
    this page's data renders as). `key` keeps the page itself in its own
    session-state slot, so it survives reruns (including the dashboard's
    own auto-refresh) as long as the caller passes the same `key` every
    time.

    Below `page_size` rows there is nothing to page through: the returned
    function then draws nothing.
    """
    total = len(df)
    state_key = f"_paginate_page_{key}"
    if total <= page_size:
        return df, lambda: None

    page_count = -(-total // page_size)
    page = min(st.session_state.get(state_key, 0), page_count - 1)
    start = page * page_size
    current_page = df.iloc[start : start + page_size]

    def controls() -> None:
        # One cluster (< 1 … 4 [5] 6 … 12 >), centered, rather than three
        # separately-gutter columns - `st.columns` always spaces its columns
        # apart, which reads fine for unrelated content but pulls buttons
        # that belong right next to each other too far apart.
        st.html(f"<style>{_PAGINATION_CSS}</style>")
        with st.container(
            horizontal=True,
            horizontal_alignment="center",
            vertical_alignment="center",
            gap="small",
            key=f"pagination-{key}",
        ):
            st.button(
                "",
                icon=":material/chevron_left:",
                key=f"{key}-prev-page",
                help="Previous page",
                disabled=page == 0,
                on_click=_shift_page,
                args=(state_key, -1, page_count),
            )
            for index, entry in enumerate(_page_window(page, page_count)):
                if entry is None:
                    st.button(
                        "…",
                        key=f"{key}-page-ellipsis-{index}",
                        disabled=True,
                    )
                    continue
                st.button(
                    str(entry + 1),
                    key=f"{key}-page-{entry}",
                    type="primary" if entry == page else "secondary",
                    disabled=entry == page,
                    on_click=_goto_page,
                    args=(state_key, entry),
                )
            st.button(
                "",
                icon=":material/chevron_right:",
                key=f"{key}-next-page",
                help="Next page",
                disabled=page >= page_count - 1,
                on_click=_shift_page,
                args=(state_key, 1, page_count),
            )

    return current_page, controls
