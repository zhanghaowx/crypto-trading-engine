"""The dashboard's card: a bordered surface with a title and its own chrome.

Every page is built out of these, so the look of one (a white surface
lifted off the canvas), the controls on it (collapse, details, hide) and
the way a group of them lays out all live here rather than in each page.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeVar

import altair as alt
import streamlit as st

from jolteon.app.components import slug

# Cards sit on the page's grey canvas (`backgroundColor` in
# .streamlit/config.toml) and would otherwise be transparent, leaving the
# whole page one flat sheet. There is no native container background
# option, so cards are painted with scoped CSS keyed to their container -
# the same escape hatch health.py uses to tint its tiles.
BACKGROUND = "#FFFFFF"

# Untitled UI's shadow-xs token - a near-invisible lift, since the card's
# own border (borderColor in config.toml) already separates it from the
# canvas.
SHADOW = "0px 1px 2px rgba(0, 0, 0, 0.05)"

# Vega charts also default to the app background, which drops a green slab
# into an otherwise white card, so they get the card's own background. The
# top padding keeps the highest series (the dashed quote rules, say) off the
# content directly above the chart.
CHART_TOP_PADDING = 20

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
            background=BACKGROUND,
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


def surface_rule(keys: Iterable[str]) -> str:
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
        f"<style>{selector} {{ background-color: {BACKGROUND};"
        f" box-shadow: {SHADOW}; }}</style>"
    )


@dataclass(frozen=True)
class Card:
    """One titled card on a page, and what goes inside it."""

    title: str
    icon: str
    body: Callable[[], None]
    actions: Callable[[], None] | None = None


_CARD_CSS = (
    Path(__file__).resolve().parent / "static" / "card.css"
).read_text()


def card_key(title: str) -> str:
    return f"card-{slug(title)}"


def cards_rule(cards: Iterable[Card]) -> str:
    """
    Returns: A style block painting each of `cards` as a surface and
    animating the height it settles at.

    Emitted before any card renders, not after: Streamlit streams
    elements to the browser as the script runs rather than painting the
    whole page at once, so a card's own container can reach the DOM
    several beats before the rule painting it white would, showing the
    canvas underneath for a moment before it snaps to white.
    """
    keys = [card_key(card.title) for card in cards]
    if not keys:
        return ""
    selector = ", ".join(f".st-key-{key}" for key in keys)
    return surface_rule(keys) + (
        f"<style>{_CARD_CSS % {'selector': selector}}</style>"
    )


def card(spec: Card) -> None:
    with st.container(border=True, key=card_key(spec.title)):
        if spec.actions is None:
            st.subheader(spec.title, icon=spec.icon)
        else:
            # A card's own action sits on the title's row instead of
            # pushing the card's content down to make room for it.
            title_col, actions_col = st.columns(
                [8, 1], vertical_alignment="center"
            )
            with title_col:
                st.subheader(spec.title, icon=spec.icon)
            with actions_col:
                spec.actions()
        spec.body()


def render_cards(cards: list[Card]) -> None:
    for spec in cards:
        card(spec)


GRID_GAP = "1rem"


def card_grid_rule(key: str, columns: int, min_width: int) -> str:
    """
    Returns: A style block laying the cards inside the container keyed
    `key` out as a masonry - at most `columns` across, none narrower than
    `min_width`, and each only as tall as its own content.

    `st.columns` fixes the number of cards per row whatever the window is
    wide enough for, and pads every row out to its tallest card; a
    multi-column layout has no rows to pad, so cards of uneven height
    (parameter groups, say) pack flush under each other and the count per
    row follows the available width.
    """
    return (
        f"<style>"
        f".st-key-{key} {{ display: block;"
        f" columns: {columns} {min_width}px;"
        f" column-gap: {GRID_GAP}; }}"
        # `contain` keeps a card's own reflow out of the column balancing:
        # without it, editing one widget relayouts every card in the grid,
        # which is most of the latency behind a click on this page.
        f".st-key-{key} > * {{ break-inside: avoid;"
        f" contain: layout style;"
        f" margin-bottom: {GRID_GAP}; }}"
        f"</style>"
    )


def card_grid(
    items,
    *,
    key: str,
    columns: int = 3,
    min_width: int = 320,
    key_fn=None,
):
    """
    Lay `items` out as a responsive masonry of bordered cards (see
    `card_grid_rule`), at most `columns` across. Yields each item with its
    own bordered container already open, so the caller just renders
    content into it - handy for pages (risk limits, health) where the
    number of cards grows over time.

    `key` keys the container the whole grid lives in, which is what the
    layout rule is scoped to, so it has to be unique within a page.

    `key_fn`, if given, computes a stable container `key` from each item,
    letting the caller target individual cards with scoped CSS (e.g. via
    `.st-key-<key>`) - such as coloring a card by status.
    """
    items = list(items)
    if not items:
        return
    # Ahead of the container: a rule arriving after the cards have reached
    # the browser leaves them stacked in one column for a moment first.
    st.html(card_grid_rule(key, min(columns, len(items)), min_width))
    with st.container(key=key):
        for item in items:
            with st.container(
                border=True, key=key_fn(item) if key_fn else None
            ):
                yield item
