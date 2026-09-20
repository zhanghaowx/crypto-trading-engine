"""The dashboard's card: a bordered surface with a title and its own chrome.

Every page is built out of these, so the look of one (a white surface
lifted off the canvas), the controls on it (collapse, details, hide) and
the way a group of them lays out all live here rather than in each page.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Literal

import streamlit as st

from jolteon.app.components import SEMANTIC_COLORS, BadgeColor

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


Accent = BadgeColor | None

CardWidth = Literal["full", "half"]

# What a card's accent is worth saying with: enough of the card's left
# edge to catch the eye from across the page, and no more, so the card
# still reads as the white surface it is.
ACCENT_WIDTH = "5px"


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


@dataclass(frozen=True)
class Card:
    """One titled card on a page, and what goes inside it.

    `id` is what the card is known by everywhere a name has to outlive
    the words on screen: its container key, whether the reader has hidden
    it, whether its details are open. The title is what the card is
    called on the page and nothing else, so it can be reworded without
    the reader's own choices about the card falling on the floor.

    `actions` draws controls of the card's own onto the title row,
    alongside the collapse, details and hide icons every card carries.
    `details` is what the card has to say beyond what it shows in
    place. Give it and the card carries a "more" icon that opens it in a
    modal; leave it out and the card carries no such icon.

    `accent` stripes the card's left edge. A card whose color says
    something that changes - a limit going from comfortable to nearly
    breached - gives a function instead of a color, which is called each
    time the card is drawn.

    `width` is how much of the page's own width a card asks for. Half
    cards pair up with the next half card on the page, so two of them
    share a row.
    """

    id: str
    title: str
    icon: str
    body: Callable[[], None]
    actions: Callable[[], None] | None = None
    details: Callable[[], None] | None = None
    accent: Accent | Callable[[], Accent] = None
    width: CardWidth = "full"


_CARD_CSS = (
    Path(__file__).resolve().parent / "static" / "card.css"
).read_text()


def card_key(card_id: str) -> str:
    return f"card-{card_id}"


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


# Where a reader's choices about a card live. Kept out of the widget keys
# below so neither can shadow the other in session state.
_HIDDEN = "_card_hidden"
_DETAILS = "_card_details"


def _hidden() -> set[str]:
    return st.session_state.setdefault(_HIDDEN, set())


# Each of these runs as a button's `on_click`, so the choice lands in
# session state *before* the rerun - the rerun's own top-to-bottom pass
# then draws the card the reader just asked for rather than the one they
# clicked on.
def _open_details(key: str) -> None:
    st.session_state[_DETAILS] = key


def _close_details() -> None:
    st.session_state.pop(_DETAILS, None)


def _hide(key: str) -> None:
    _hidden().add(key)
    if st.session_state.get(_DETAILS) == key:
        _close_details()


def _unhide_all() -> None:
    _hidden().clear()


def _details_dialog(spec: Card, details: Callable[[], None]) -> None:
    """
    What the card has to say beyond what it shows in place, in a modal
    of its own - wide enough for the tables a card has to squeeze.

    Opened from session state rather than straight from the button's own
    return value: the pages this renders on refresh on a timer, and a
    modal opened by a click alone would close again on the first refresh
    after it.
    """
    st.dialog(
        spec.title,
        icon=spec.icon,
        width="large",
        on_dismiss=_close_details,
    )(details)()


def _chrome(spec: Card, key: str) -> None:
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
        key=f"card-chrome-{spec.id}",
    ):
        if spec.actions is not None:
            spec.actions()
        # Only where there is something more to show: an icon on a card
        # that has nothing behind it promises a detail that is not there.
        if spec.details is not None:
            st.button(
                "",
                icon=":material/more_horiz:",
                key=f"{key}-details",
                help="Show more detail.",
                type="tertiary",
                on_click=_open_details,
                args=(key,),
            )
        st.button(
            "",
            icon=":material/close:",
            key=f"{key}-hide",
            help="Hide this card until the page is reloaded.",
            type="tertiary",
            on_click=_hide,
            args=(key,),
        )


def card(spec: Card) -> None:
    # Whether a card is hidden at all is settled by `_rows`, which drops
    # the hidden ones before pairing the rest into their rows.
    key = card_key(spec.id)
    # A card's content is drawn in one place at a time: on the page, or
    # in the modal, never both. Anything inside it that keys a widget or
    # a container of its own - the risk gauges, the page through recent
    # fills - would otherwise be asked for twice in the same run, which
    # Streamlit refuses.
    in_modal = (
        spec.details is not None and st.session_state.get(_DETAILS) == key
    )
    accent = spec.accent() if callable(spec.accent) else spec.accent
    # With the card's own container rather than with the page's other
    # rules: an accent that reports on live data is only known once the
    # card is being drawn.
    if rule := accent_rule(key, accent):
        st.html(rule)
    with st.container(border=True, key=key):
        # Collapsing is the expander's own doing, and it does it in the
        # browser: the content is already there, so folding it away costs
        # no rerun, no re-read of the recording, and no chart redraw. A
        # button of ours would have had to ask the server instead, which
        # is what made expanding a card take the best part of a second.
        with st.expander(f"{spec.icon} {spec.title}", expanded=True):
            if not in_modal:
                spec.body()
        # After the expander, not before: it is positioned over the
        # expander's own summary row by `card.css`, and a later sibling
        # wins the stacking order without needing a z-index.
        _chrome(spec, key)
    if in_modal and spec.details is not None:
        _details_dialog(spec, spec.details)


def _unhide_control(cards: list[Card]) -> None:
    """
    The way back to a card the reader has closed.

    Without one a card hidden on a page that refreshes on a timer is
    unreachable until the whole dashboard is reloaded, which is a steep
    price for a click on an icon the size of this one.
    """
    hidden = [spec for spec in cards if card_key(spec.id) in _hidden()]
    if not hidden:
        return
    with st.container(horizontal=True, horizontal_alignment="center"):
        st.button(
            f"Show {', '.join(spec.title for spec in hidden)}",
            icon=":material/visibility:",
            key="card-unhide",
            type="tertiary",
            on_click=_unhide_all,
        )


def _rows(cards: list[Card]) -> Iterator[list[Card]]:
    """
    The cards grouped into the rows they are drawn in: a full-width card
    on a row of its own, half-width cards two to a row.

    Hidden cards are left out before the pairing rather than after, so
    closing one of a pair promotes the next card up beside its partner
    instead of leaving a gap where it was.
    """
    row: list[Card] = []
    for spec in cards:
        if card_key(spec.id) in _hidden():
            continue
        if spec.width == "full":
            if row:
                yield row
                row = []
            yield [spec]
            continue
        row.append(spec)
        if len(row) == 2:
            yield row
            row = []
    if row:
        yield row


def _require_unique_ids(cards: list[Card]) -> None:
    """
    Two cards sharing an id would share a container key, a hidden flag
    and a details flag, so hiding one would hide the other and neither
    would ever be drawn on its own.
    """
    ids = [spec.id for spec in cards]
    repeated = {card_id for card_id in ids if ids.count(card_id) > 1}
    if repeated:
        raise ValueError(f"Cards share an id: {', '.join(sorted(repeated))}")


def render_cards(cards: list[Card]) -> None:
    _require_unique_ids(cards)
    for row in _rows(cards):
        if len(row) == 1:
            card(row[0])
            continue
        for column, spec in zip(st.columns(len(row)), row):
            with column:
                card(spec)
    _unhide_control(cards)


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
