"""The book drawn out level by level, bids beside asks, with our quotes
in it."""

import math
import re
from html import escape
from pathlib import Path

import streamlit as st

from jolteon.dashboard.read_models.order_book import (
    Quote,
    book_now,
    our_quotes,
    recorded_symbol,
)
from jolteon.dashboard.ui.empty_states import empty_state, warn_if_no_db
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

# Each side's bar grows from the middle of the card outwards - bids from
# their right edge, asks from their left - so the two sides read as one
# book folded open at the spread.
_DEPTH_FROM = {
    "bid": "to left",
    "ask": "to right",
}

_BOOK_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "order_book.css"
).read_text()

_OURS_TAG = '<span class="jolteon-book-ours">ours</span>'


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


def _price_cell(price: float, ours: bool) -> str:
    """The price, tagged where the quote at it is ours. The tag goes
    before the figure, so the prices still line up down the column."""
    tag = _OURS_TAG if ours else ""
    return f'<td class="jolteon-book-price">{tag}{price:,.2f}</td>'


def _our_row(quote: Quote, side: str) -> str:
    """Our quote on a line of its own, for where no one else is resting -
    quoting inside the spread puts us at a price the book has no level
    at, and in paper trading our orders never reach the venue's book at
    all."""
    size = "–" if quote.quantity is None else f"{quote.quantity:,.4f}"
    return (
        f'<tr class="jolteon-book-row jolteon-book-{side} '
        f'jolteon-book-resting jolteon-book-alone">'
        f"{_price_cell(quote.price, True)}"
        f"<td>{size}</td>"
        # Our own order is no part of the venue's resting depth, so it
        # has no running total to carry.
        f"<td>–</td>"
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
        f"background:linear-gradient({_DEPTH_FROM[side]},"
        f"{tint} 0 {fill:.1f}%,transparent {fill:.1f}% 100%)"
    )
    return (
        f'<tr class="{classes}" style="{bar}">'
        f"{_price_cell(level.price, ours)}"
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
    its own side, rather than dropping out of the book entirely.
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


def _currencies(symbol: str) -> tuple[str, str]:
    """The base and quote currency a symbol names, and nothing at all
    where the recording does not name it as a pair."""
    parts = re.split(r"[/-]", symbol, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", "")


def _side_html(side: str, rows: list[str], base: str, quote: str) -> str:
    heading = "Bids" if side == "bid" else "Asks"
    currency = f" <span>· {escape(quote)}</span>" if quote else ""
    unit = f" ({escape(base)})" if base else ""
    return (
        f'<div class="jolteon-book-side jolteon-book-{side}s">'
        f"<h3>{heading}{currency}</h3>"
        f"<table><thead><tr><th>Price</th><th>Size{unit}</th>"
        f"<th>Total</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def book_html(book: OrderBook, quotes: dict[str, Quote], symbol: str) -> str:
    """
    Returns: The book as two columns - bids on the left, asks on the
    right, each best price first - every level backed by a bar the width
    of everything resting at it and ahead of it, our own quote placed in
    it, and the mid and spread between the two sides' best prices under
    them.
    """
    bids = _rows(book.bids(LEVELS))
    asks = _rows(book.asks(LEVELS))
    deepest = max(
        [total for _, total in bids] + [total for _, total in asks] + [0.0]
    )
    base, quote_currency = _currencies(symbol)

    bid_rows = _side_rows(bids, deepest, "bid", quotes.get("BUY"))
    ask_rows = _side_rows(asks, deepest, "ask", quotes.get("SELL"))

    best_bid, best_ask = book.best_bid(), book.best_ask()
    if best_bid and best_ask:
        spread = best_ask.price - best_bid.price
        mid = (best_ask.price + best_bid.price) / 2
        in_currency = f" {escape(quote_currency)}" if quote_currency else ""
        middle = (
            f'<div class="jolteon-book-mid"><span>Mid price</span>'
            f"<strong>{mid:,.2f}</strong>"
            f"<span>Spread <b>{spread:,.2f}</b>{in_currency}"
            f" · {spread / mid * 1e4:,.1f} bps</span></div>"
        )
    else:
        middle = ""

    return (
        f"<style>{_BOOK_CSS}</style>"
        f'<div class="jolteon-book"><div class="jolteon-book-sides">'
        f"{_side_html('bid', bid_rows, base, quote_currency)}"
        f"{_side_html('ask', ask_rows, base, quote_currency)}"
        f"</div>{middle}</div>"
    )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    symbol = recorded_symbol(db_path)
    book = book_now(db_path, symbol)
    if book is None or not book.bbo():
        empty_state("No order book recorded yet that this page can read.")
        return

    st.html(book_html(book, our_quotes(db_path), symbol))
