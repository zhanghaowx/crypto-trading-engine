"""Shared UI helpers used by more than one dashboard page."""

import re
from pathlib import Path
from typing import Literal, TypeVar

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

# A shallow, low-opacity drop shadow in the theme's near-black, enough to
# lift the cards off the canvas without reading as a heavy border.
CARD_SHADOW = "0 2px 6px rgba(21, 23, 28, 0.07)"

# Vega charts also default to the app background, which drops a green slab
# into an otherwise white card, so they get the card's own background. The
# top padding keeps the highest series (the dashed quote rules, say) off the
# content directly above the chart.
CHART_TOP_PADDING = 20

# Dataframe interiors follow `theme.backgroundColor`, so inside a white card
# they'd show as a grey hole. Only the header and border are theme-settable
# (`dataframeHeaderBackgroundColor` / `dataframeBorderColor` in config.toml),
# so the body is painted through a pandas Styler instead - in the card's own
# white, leaving the grey header band and gridlines to delineate the table.

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
    the grey page background inside a white card.
    """
    return df.style.set_properties(**{"background-color": CARD_BACKGROUND})


_FLASH_ANIMATION = "jolteon-flash"
_FLASH_KEYFRAMES = f"""
@keyframes {_FLASH_ANIMATION} {{
  from {{ background-color: rgba(21, 23, 28, 0.12); }}
  to {{ background-color: transparent; }}
}}
"""


def flash_key(*parts: str) -> str:
    """
    A container `key` that changes exactly when `parts` do.

    Streamlit reuses a widget's DOM node across reruns unless its `key`
    changes, so folding a value into the key is what forces the remount a
    CSS animation needs in order to play again once that value updates.
    """
    return "flash-" + re.sub(
        r"[^a-z0-9]+", "-", "-".join(parts).lower()
    ).strip("-")


def flash_rule(*keys: str) -> str:
    """CSS making every container keyed by `flash_key` pulse once when it
    mounts. Empty if there are no keys, rather than an empty style tag."""
    if not keys:
        return ""
    selector = ", ".join(f".st-key-{key}" for key in keys)
    return (
        f"{_FLASH_KEYFRAMES}{selector} "
        f"{{ animation: {_FLASH_ANIMATION} 900ms ease-out; }}"
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
    help: str | None = None,
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
        help=help,
        border=border,
        key=key,
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


def warn_if_no_db(db_path: str | None = None) -> bool:
    """Returns whether `db_path` (the main database by default) exists."""
    db_path = db_path or st.session_state.db_path
    if Path(db_path).exists():
        return True
    st.warning(
        f"No database found at `{db_path}` yet. "
        f"Waiting for the engine to start recording... "
        f"(check the Parameters tab if this looks wrong)"
    )
    return False
