"""Shared UI helpers used by more than one dashboard page."""

from pathlib import Path
from typing import Literal, TypeVar

import altair as alt
import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

# Cards (the bordered section containers) sit on the sage canvas
# (`backgroundColor` in .streamlit/config.toml) and would otherwise be
# transparent, leaving the whole page one flat sheet. There is no native
# container background option, so cards are painted with scoped CSS keyed to
# their container - the same escape hatch health.py uses to tint its tiles.
CARD_BACKGROUND = "#FFFFFF"

# A shallow, low-opacity drop shadow in the theme's near-black, enough to
# lift the cards off the canvas without reading as a heavy border.
CARD_SHADOW = "0 2px 6px rgba(21, 23, 28, 0.07)"

# Vega charts also default to the app background, which drops a green slab
# into an otherwise white card, so they get the card's own background. The
# top padding keeps the highest series (the dashed quote rules, say) off the
# content directly above the chart.
CHART_TOP_PADDING = 20

# Dataframe interiors follow `theme.backgroundColor`, so inside a white card
# they'd show as a sage hole. Only the header and border are theme-settable
# (`dataframeHeaderBackgroundColor` / `dataframeBorderColor` in config.toml),
# so the body is painted through a pandas Styler instead - in the card's own
# white, leaving the sage header band and gridlines to delineate the table.

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
    part of the card rather than as a colored panel dropped into it.
    """
    return chart.properties(
        background=CARD_BACKGROUND,
        padding={"top": CHART_TOP_PADDING, "left": 5, "right": 5, "bottom": 5},
    )


def style_table(df: pd.DataFrame) -> Styler:
    """
    Give a dataframe the card's white interior, so it doesn't fall back to
    the sage page background inside a white card.
    """
    return df.style.set_properties(**{"background-color": CARD_BACKGROUND})


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
