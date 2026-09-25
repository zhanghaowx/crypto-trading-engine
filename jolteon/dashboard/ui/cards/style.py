"""The CSS that makes a Streamlit container read as a card.

Streamlit has no background, shadow or accent option on a container, so
every one of these is a rule scoped to the container's own key. They are
emitted before the containers they paint reach the browser.
"""

from pathlib import Path
from typing import Iterable

from jolteon.dashboard.ui.cards.model import Accent, Card, card_key
from jolteon.dashboard.ui.primitives import SEMANTIC_COLORS

# What a card's accent is worth saying with: enough of the card's left
# edge to catch the eye from across the page, and no more, so the card
# still reads as the white surface it is.
ACCENT_WIDTH = "5px"

# Cards sit on the page's canvas (`backgroundColor` in
# .streamlit/config.toml) and would otherwise be transparent, leaving the
# whole page one flat sheet. There is no native container background
# option, so cards are painted with scoped CSS keyed to their container -
# the same escape hatch health.py uses to tint its tiles.
BACKGROUND = "#FFFFFF"


def surface_rule(keys: Iterable[str]) -> str:
    """
    Returns: A style block painting the given container keys as cards.

    Streamlit has no container background option, so every page that
    wants a card to read as a white surface above the canvas rather than
    a flat patch of it needs this same scoped rule. The card's own
    border (borderColor in config.toml) is what separates it from the
    canvas - no shadow is drawn on top of that.
    """
    selector = ", ".join(f".st-key-{key}" for key in keys)
    if not selector:
        return ""
    return f"<style>{selector} {{ background-color: {BACKGROUND}; }}</style>"


def accent_rule(key: str, accent: Accent) -> str:
    """
    Returns: A style block striping the left edge of the card keyed `key`
    in `accent`, empty for a card with no accent to draw.
    """
    if accent is None:
        return ""
    return (
        f"<style>.st-key-{key} {{ border-left:"
        f" {ACCENT_WIDTH} solid {SEMANTIC_COLORS[accent]}; }}</style>"
    )


_CARD_CSS = (
    Path(__file__).resolve().parents[2] / "static" / "card.css"
).read_text()


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
    keys = [card_key(card.id) for card in cards]
    if not keys:
        return ""
    # `:is(...)`, not a bare comma list: the rules below scope descendants
    # of a card, and in `.a, .b desc` the descendant part binds only to
    # `.b` - every earlier card would take the rule on itself instead.
    selector = ":is(" + ", ".join(f".st-key-{key}" for key in keys) + ")"
    return surface_rule(keys) + (
        f"<style>{_CARD_CSS % {'selector': selector}}</style>"
    )


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
