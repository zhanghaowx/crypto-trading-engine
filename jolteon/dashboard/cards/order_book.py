"""The ladder: the book drawn out level by level, with our quotes in it."""

import math
from pathlib import Path

import streamlit as st

from jolteon.dashboard.read_models.order_book import (
    Quote,
    book_now,
    our_quotes,
    recorded_symbol,
)
from jolteon.dashboard.ui.empty_states import warn_if_no_db
from jolteon.dashboard.ui.primitives import NEGATIVE_RGB, POSITIVE_RGB
from jolteon.engine.market_data.core.order_book import OrderBook, PriceLevel

LEVELS = 10


def _tint(rgb: tuple[int, int, int]) -> str:
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.13)"


# The depth bar's tint per side, matching the price colour beside it.
_DEPTH_TINT = {
    "bid": _tint(POSITIVE_RGB),
    "ask": _tint(NEGATIVE_RGB),
}

_LADDER_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "order_book.css"
).read_text()


def _rows(levels: list[PriceLevel]) -> list[tuple[PriceLevel, float]]:
    """Each level paired with the quantity resting at it and everything
    ahead of it - what a taker would have to clear to reach it."""
    running = 0.0
    paired = []
    for level in levels:
        running += level.quantity
        paired.append((level, running))
    return paired


def _same_price(one: float, other: float) -> bool:
    """Whether two recorded prices name the same level. Compared with a
    tolerance rather than exactly: our order's price and the venue's
    level reach the recording by different routes, and two floats that
    print the same need not be the same float."""
    return math.isclose(one, other, rel_tol=1e-9, abs_tol=0.0)


def _our_row(quote: Quote, side: str) -> str:
    """Our quote on a line of its own, for where no one else is resting -
    quoting inside the spread puts us at a price the book has no level
    at, and in paper trading our orders never reach the venue's book at
    all."""
    size = "\u2013" if quote.quantity is None else f"{quote.quantity:,.4f}"
    return (
        f'<tr class="jolteon-book-row jolteon-book-{side} '
        f'jolteon-book-resting jolteon-book-alone">'
        f'<td class="jolteon-book-price">{quote.price:,.2f}</td>'
        f"<td>{size}</td>"
        # Our own order is no part of the venue's resting depth, so it
        # has no running total to carry.
        f"<td>\u2013</td>"
        f"</tr>"
    )


def _ladder_row(
    level: PriceLevel,
    cumulative: float,
    deepest: float,
    side: str,
    ours: bool,
) -> str:
    fill = (cumulative / deepest * 100) if deepest else 0.0
    classes = f"jolteon-book-row jolteon-book-{side}"
    if ours:
        classes += " jolteon-book-resting"
    # The depth bar is a gradient on the row itself rather than a box in
    # a cell of its own: it has to span every column to show the shape of
    # the resting size behind the numbers, the way a venue's book does.
    tint = _DEPTH_TINT[side]
    bar = (
        f"background:linear-gradient(to left,{tint} 0 {fill:.1f}%,"
        f"transparent {fill:.1f}% 100%)"
    )
    return (
        f'<tr class="{classes}" style="{bar}">'
        f'<td class="jolteon-book-price">{level.price:,.2f}</td>'
        f"<td>{level.quantity:,.4f}</td>"
        f"<td>{cumulative:,.4f}</td>"
        f"</tr>"
    )


def _side_rows(
    paired: list[tuple[PriceLevel, float]],
    deepest: float,
    side: str,
    quote: Quote | None,
) -> list[str]:
    """
    Returns: One side's rows, best price first.

    Our quote marks the level it rests at where the venue has one at that
    price, and takes a row of its own where it does not - which is what a
    quote inside the spread always does. A quote further out than the
    levels shown keeps its place in the price order, at the far end of
    its own side, rather than dropping out of the ladder entirely.
    """
    ahead = (
        (lambda ours, theirs: ours > theirs)
        if side == "bid"
        else (lambda ours, theirs: ours < theirs)
    )
    rows: list[str] = []
    placed = quote is None
    for level, total in paired:
        if quote is not None and not placed:
            if _same_price(level.price, quote.price):
                rows.append(_ladder_row(level, total, deepest, side, True))
                placed = True
                continue
            if ahead(quote.price, level.price):
                rows.append(_our_row(quote, side))
                placed = True
        rows.append(_ladder_row(level, total, deepest, side, False))
    if quote is not None and not placed:
        rows.append(_our_row(quote, side))
    return rows


def _column(label: str, side: str, rows: str) -> str:
    # Wrapped in its own scrolling div rather than left to overflow the
    # card: a table's overflow is unreliable without a block-level box of
    # its own to size and scroll within.
    return (
        f'<div class="jolteon-book-col">'
        f'<table class="jolteon-book jolteon-book-{side}">'
        f"<caption>{label}</caption>"
        f"<thead><tr><th>Price</th><th>Size</th>"
        f"<th>Total</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"</div>"
    )


def ladder_html(book: OrderBook, quotes: dict[str, Quote]) -> str:
    """
    Returns: The book as two columns, best price at the top of each -
    bids on the left, asks on the right - each level backed by a bar the
    width of everything resting at it and ahead of it on its own side,
    and our own quote placed in whichever column it belongs to. One
    depth scale is shared across both columns, so a heavier side reads
    as visibly heavier rather than each side filling its own bar alone.
    """
    bids = _rows(book.bids(LEVELS))
    asks = _rows(book.asks(LEVELS))
    deepest = max(
        [total for _, total in bids] + [total for _, total in asks] + [0.0]
    )

    bid_rows = "".join(_side_rows(bids, deepest, "bid", quotes.get("BUY")))
    ask_rows = "".join(_side_rows(asks, deepest, "ask", quotes.get("SELL")))

    best_bid, best_ask = book.best_bid(), book.best_ask()
    if best_bid and best_ask:
        spread = best_ask.price - best_bid.price
        mid = (best_ask.price + best_bid.price) / 2
        summary = (
            f'<div class="jolteon-book-summary">'
            f'<span class="jolteon-book-mid">{mid:,.2f}</span>'
            f"<span>spread {spread:,.2f}"
            f" ({spread / mid * 1e4:,.1f} bps)</span>"
            f"</div>"
        )
    else:
        summary = ""

    return (
        f"<style>{_LADDER_CSS}</style>"
        f'<div class="jolteon-book-columns">'
        f"{_column('Bids', 'bid', bid_rows)}"
        f"{_column('Asks', 'ask', ask_rows)}"
        f"</div>{summary}"
    )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    book = book_now(db_path, recorded_symbol(db_path))
    if book is None or not book.bbo():
        st.info("No order book recorded yet that this page can read.")
        return

    st.html(ladder_html(book, our_quotes(db_path)))
