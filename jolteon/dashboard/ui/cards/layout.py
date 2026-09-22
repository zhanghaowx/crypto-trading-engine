"""How a page's cards are arranged: rows, pairs and grids."""

from typing import Iterator

import streamlit as st

from jolteon.dashboard.ui.cards.model import Card, card_key
from jolteon.dashboard.ui.cards.runtime import card, hidden_keys, unhide_all
from jolteon.dashboard.ui.cards.style import card_grid_rule


def _unhide_control(cards: list[Card]) -> None:
    """
    The way back to a card the reader has closed.

    Without one a card hidden on a page that refreshes on a timer is
    unreachable until the whole dashboard is reloaded, which is a steep
    price for a click on an icon the size of this one.
    """
    hidden = [spec for spec in cards if card_key(spec.id) in hidden_keys()]
    if not hidden:
        return
    # Outside card fragments: showing cards must repack rows and register
    # their timers, so this control intentionally reruns the full page.
    with st.container(horizontal=True, horizontal_alignment="center"):
        st.button(
            f"Show {', '.join(spec.title for spec in hidden)}",
            icon=":material/visibility:",
            key="card-unhide",
            type="tertiary",
            on_click=unhide_all,
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
        if card_key(spec.id) in hidden_keys():
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
