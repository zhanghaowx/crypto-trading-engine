"""Shared UI helpers used by more than one dashboard page."""

import re
from pathlib import Path
from typing import Callable, Literal

import pandas as pd
import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.data.sqlite import database_exists
from jolteon.dashboard.settings import ENGINE

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


# The theme's semantic colors (`.streamlit/config.toml`). Streamlit hands
# these to a badge by name but to nothing drawn by hand, so a status dot,
# a gauge arc or a card's accent has to name the hex itself.
SEMANTIC_COLORS: dict[BadgeColor, str] = {
    "red": "#DC2626",
    "orange": "#E8873C",
    "yellow": "#E8B93C",
    "blue": "#3E8FD0",
    "green": "#16A34A",
    "violet": "#8B7EF0",
    "gray": "#8A8D91",
    "grey": "#8A8D91",
    "primary": "#15171C",
}

POSITIVE_COLOR = SEMANTIC_COLORS["green"]
NEGATIVE_COLOR = SEMANTIC_COLORS["red"]


# What a figure the recording cannot answer for reads as, everywhere
# one is shown: an en dash rather than a zero or a blank cell.
MISSING = "\u2013"


def sign_color(value: float) -> BadgeColor:
    """A signed value's color, the way quotes are colored elsewhere."""
    return "green" if value >= 0 else "red"


def fmt_usd(value: float) -> str:
    """A signed dollar amount, and an en dash where there is no figure -
    a horizon a fill has not reached yet is not zero dollars."""
    if pd.isna(value):
        return MISSING
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def metric(
    label: str,
    value: float,
    *,
    decimals: int | None = 2,
    color: BadgeColor | None = None,
    prefix: str = "",
    suffix: str = "",
    border: bool = False,
    help: str | None = None,
) -> None:
    """A metric whose number is formatted and, given a `color`, drawn in
    one of the theme's semantic colors rather than the body text color."""
    shown = f"{value:,}" if decimals is None else f"{value:,.{decimals}f}"
    shown = f"{prefix}{shown}{suffix}"
    st.metric(
        label,
        f":{color}[{shown}]" if color else shown,
        border=border,
        help=help,
    )


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


POSITIVE_RGB = hex_to_rgb(POSITIVE_COLOR)
NEGATIVE_RGB = hex_to_rgb(NEGATIVE_COLOR)


_PAGINATION_CSS = (
    Path(__file__).resolve().parent / "static" / "pagination.css"
).read_text()


def slug(text: str) -> str:
    """`text` as a CSS-safe fragment of a container key."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def row_key(prefix: str, identity: str) -> str:
    """
    A container `key` for a row/entry, stable for as long as its own
    `identity` is (e.g. a fill's trade id, a log line's timestamp) -
    *not* its position in a list, which shifts as newer rows arrive.

    Streamlit keeps a container's DOM node across reruns as long as its
    key is unchanged, so an existing row is left alone rather than being
    torn down and rebuilt on every refresh.
    """
    return f"row-{prefix}-{slug(identity)}"


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


def select_engine() -> None:
    """
    Which engine's recording the page below reads.

    One engine trades one symbol and records to its own file, so choosing
    a symbol is choosing a database - which `init_settings` resolves from
    the choice this leaves behind. Nothing is offered while only one
    engine has been running, since there is nothing to choose between.
    """
    engines = engine_databases(st.session_state.root)
    if len(engines) < 2:
        return

    st.segmented_control(
        "Symbol",
        options=[engine.key for engine in engines],
        default=engines[0].key,
        format_func=lambda key: next(
            engine.label for engine in engines if engine.key == key
        ),
        # A page that reads one engine has to be reading one: cleared,
        # everything below would go on showing the engine the reader had
        # just stopped asking for.
        required=True,
        key=ENGINE,
        # The binding carries the symbol in the URL, so a link names the
        # symbol it was copied from. `persist_state` is what carries it
        # across a page switch: a bound value belongs to the page that
        # bound it, and is dropped from the URL on the way to another.
        bind="query-params",
        persist_state="session",
        label_visibility="collapsed",
    )


# What a run's status is called on screen. The recording's own "open" is
# settled into one of these by `health_summary.resolve_run`.
_RUN_STATUS_LABELS = {
    "running": "Running",
    "stopped": "Stopped",
    "interrupted": "Interrupted",
}


def run_status(run: RecordedEngineRun) -> str:
    """A run's status in the words a reader sees, the same on every page."""
    return _RUN_STATUS_LABELS[run.status]


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
