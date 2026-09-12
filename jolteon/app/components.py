"""Shared UI helpers used by more than one dashboard page."""

import re
from pathlib import Path
from typing import Callable, Literal, TypeVar

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pandas.io.formats.style import Styler

# Cards (the bordered section containers) sit on the page's grey canvas
# (`backgroundColor` in .streamlit/config.toml) and would otherwise be
# transparent, leaving the whole page one flat sheet. There is no native
# container background option, so cards are painted with scoped CSS keyed to
# their container - the same escape hatch health.py uses to tint its tiles.
CARD_BACKGROUND = "#FFFFFF"

# Untitled UI's shadow-xs token - a near-invisible lift, since the card's
# own border (borderColor in config.toml) already separates it from the
# canvas.
CARD_SHADOW = "0px 1px 2px rgba(0, 0, 0, 0.05)"

# Vega charts also default to the app background, which drops a green slab
# into an otherwise white card, so they get the card's own background. The
# top padding keeps the highest series (the dashed quote rules, say) off the
# content directly above the chart.
CHART_TOP_PADDING = 20

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


ChartT = TypeVar("ChartT", bound=alt.TopLevelMixin)


def style_chart(chart: ChartT) -> ChartT:
    """
    Give a chart the card's white ground and some headroom, so it reads as
    part of the card rather than as a colored panel dropped into it. Also
    drops the axis lines/ticks and the vertical gridlines (Untitled UI's
    `CartesianGrid vertical={false}`, stroked in its neutral-100), leaving
    only faint horizontal gridlines so the data reads over the chrome
    instead of competing with it.
    """
    return (
        chart.properties(
            background=CARD_BACKGROUND,
            padding={
                "top": CHART_TOP_PADDING,
                "left": 5,
                "right": 5,
                "bottom": 5,
            },
        )
        .configure_view(strokeWidth=0)
        .configure_axis(domain=False, ticks=False, grid=False)
        .configure_axisY(grid=True, gridColor="#F5F5F5", gridDash=[0])
    )


POSITIVE_COLOR = "#16A34A"
NEGATIVE_COLOR = "#DC2626"


def sign_color(value: float) -> str:
    """A signed value's color, the way quotes are colored elsewhere."""
    return POSITIVE_COLOR if value >= 0 else NEGATIVE_COLOR


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


POSITIVE_RGB = hex_to_rgb(POSITIVE_COLOR)
NEGATIVE_RGB = hex_to_rgb(NEGATIVE_COLOR)


def shade_cell(value: float, scale: float) -> str:
    """A background tint for a signed cell, deeper the further `value`
    sits from zero relative to `scale` (the column's own largest
    magnitude) - so the standout numbers in a row of tightly-packed
    figures read through color, not through font size."""
    if pd.isna(value) or scale == 0:
        return ""
    intensity = min(abs(value) / scale, 1.0)
    r, g, b = POSITIVE_RGB if value >= 0 else NEGATIVE_RGB
    alpha = 0.10 + 0.35 * intensity
    return f"background-color: rgba({r}, {g}, {b}, {alpha:.2f})"


def shade_column(column: pd.Series) -> list[str]:
    scale = column.abs().max()
    return [shade_cell(value, scale) for value in column]


def styled_table(
    table: pd.DataFrame,
    shaded_columns: list[str],
    format_fn: Callable[[float], str],
) -> Styler:
    """`table`, formatted with `format_fn` and shaded by `shade_column` on
    `shaded_columns` - the caller still owns rendering it (`st.dataframe`)
    and can chain further `.apply()` calls (e.g. a side-specific tint)
    before doing so."""
    styled = table.style.format({col: format_fn for col in shaded_columns})
    return styled.apply(shade_column, subset=shaded_columns, axis=0)


_ROW_ANIMATIONS_CSS = (
    Path(__file__).resolve().parent / "static" / "row_animations.css"
).read_text()


def row_key(prefix: str, identity: str) -> str:
    """
    A container `key` for a row/entry, stable for as long as its own
    `identity` is (e.g. a fill's trade id, a log line's timestamp) -
    *not* its position in a list, which shifts as newer rows arrive.

    Streamlit keeps a container's DOM node across reruns as long as its
    key is unchanged, so an existing row is left alone (no replayed
    animation) while a row whose identity has never been seen before
    mounts fresh - which is what `row_add_rule` needs to play once, only
    for the row that's actually new.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", identity.lower()).strip("-")
    return f"row-{prefix}-{slug}"


def row_add_rule(prefix: str) -> str:
    """
    CSS making every container keyed by `row_key(prefix, ...)` slide down,
    fade in, and briefly highlight when it mounts - once per row, however
    many rows exist, since only a brand-new key ever triggers a mount.
    """
    return (
        f'{_ROW_ANIMATIONS_CSS}[class*="st-key-row-{prefix}-"] '
        f"{{ animation: jolteon-row-add 350ms ease-out; }}"
    )


_ANIMATED_METRIC_DIR = (
    Path(__file__).resolve().parent / "static" / "animated_metric"
)
_animated_metric = components.declare_component(
    "animated_metric", path=str(_ANIMATED_METRIC_DIR)
)


def animated_metric(
    key: str,
    label: str,
    value: float,
    *,
    decimals: int | None = 2,
    color: str | None = None,
    prefix: str = "",
    suffix: str = "",
    border: bool = False,
) -> None:
    """
    A metric tile whose number rolls, digit by digit, to its new value
    (via NumberFlow - see jolteon/app/static/animated_metric) rather than
    just replacing the old text - `st.metric` has no such transition.

    `key` must stay stable for a given metric across reruns: Streamlit
    then keeps this component's iframe mounted and delivers new args into
    it in place, instead of recreating the iframe (which `st.metric` and
    `st.html` both effectively do on every rerun) - a fresh element has no
    previous value to animate from.
    """
    _animated_metric(
        label=label,
        value=value,
        decimals=decimals,
        color=color,
        prefix=prefix,
        suffix=suffix,
        border=border,
        key=key,
    )


def card_surface_rule(keys) -> str:
    """
    Returns: A style block painting the given container keys as cards.

    Streamlit has no container background option, so every page that
    wants a card to read as a white surface above the canvas rather than
    a flat patch of it needs this same scoped rule.
    """
    selector = ", ".join(f".st-key-{key}" for key in keys)
    if not selector:
        return ""
    return (
        f"<style>{selector} {{ background-color: {CARD_BACKGROUND};"
        f" box-shadow: {CARD_SHADOW}; }}</style>"
    )


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
        with st.container(
            horizontal=True,
            horizontal_alignment="center",
            vertical_alignment="center",
            gap="small",
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


def warn_if_no_db(db_path: str | None = None) -> bool:
    """Returns whether `db_path` (the main database by default) exists."""
    db_path = db_path or st.session_state.db_path
    if Path(db_path).exists():
        return True
    st.warning(
        f"No database found at `{db_path}` yet. "
        f"Waiting for the engine to start recording... "
        f"(check the Parameters page if this looks wrong)"
    )
    return False
