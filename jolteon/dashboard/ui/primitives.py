"""The small pieces every page draws with: colors, figures, keys.

Nothing here reads a recording or holds state; it is how a number, a
status color or a container key is spelled, kept in one place so two
pages cannot spell the same thing differently.
"""

import re
from typing import Literal

import pandas as pd
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
