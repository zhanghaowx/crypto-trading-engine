"""The book as it stands, and where our own quotes sit in it.

The engine records each normalised book update rather than the book
itself (see RecordedBookUpdate), so the current book is rebuilt here by
replaying from the last snapshot. That keeps the recording narrow - a
book written out level by level widens its table every time the book
moves - and leaves the dashboard to do the assembling.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.app.components import warn_if_no_db
from jolteon.app.data import read_latest_per_group, read_table
from jolteon.engine.market_data.core.order_book import (
    OrderBook,
    PriceLevel,
    RecordedBookUpdate,
)

LEVELS = 10


@dataclass(frozen=True)
class Quote:
    """One of our own resting orders, as the ladder places it. The size
    is what the order was placed for, and is not always recorded."""

    price: float
    quantity: float | None = None


# The depth bar's tint per side, matching the price colour beside it.
_DEPTH_TINT = {
    "bid": "rgba(22, 163, 74, 0.13)",
    "ask": "rgba(220, 38, 38, 0.13)",
}

_LADDER_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "order_book.css"
).read_text()


def rebuild(updates: pd.DataFrame, symbol: str) -> OrderBook | None:
    """
    Returns: The book as the last recorded update left it, or nothing at
    all when no snapshot has been recorded to replay from.

    Only the updates from the newest snapshot onward are applied: every
    one before it is superseded by that snapshot, and a session's worth
    of increments would otherwise be replayed on every refresh.
    """
    if updates.empty or "is_snapshot" not in updates.columns:
        return None

    ordered = updates.sort_values("sequence")
    snapshots = ordered.index[ordered["is_snapshot"].astype(bool)]
    if snapshots.empty:
        return None

    book = OrderBook(symbol)
    for row in ordered.loc[snapshots[-1] :].itertuples():
        recorded = RecordedBookUpdate(
            symbol=symbol,
            model=row.model,
            version=int(row.version),
            sequence=int(row.sequence),
            bids=row.bids,
            asks=row.asks,
            is_snapshot=bool(row.is_snapshot),
            exchange_time=row.exchange_time,
        )
        try:
            book.apply(recorded.to_update())
        except ValueError:
            # A recording this dashboard cannot read - a later book model
            # than it knows about. Saying so beats taking the page down.
            return None
    return book


def _rows(levels: list[PriceLevel]) -> list[tuple[PriceLevel, float]]:
    """Each level paired with the quantity resting at it and everything
    ahead of it - what a taker would have to clear to reach it."""
    running = 0.0
    paired = []
    for level in levels:
        running += level.quantity
        paired.append((level, running))
    return paired


def our_quotes(db_path: str) -> dict[str, Quote]:
    """Our own latest order on each side, which is what the ladder places
    so a reader can see where we are resting."""
    quotes = read_latest_per_group(db_path, "order", "side")
    if quotes.empty or "price" not in quotes.columns:
        return {}
    sized = "quantity" in quotes.columns
    return {
        str(row.side): Quote(
            float(row.price),
            float(row.quantity) if sized and pd.notna(row.quantity) else None,
        )
        for row in quotes.itertuples()
        if pd.notna(row.price)
    }


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


def ladder_html(book: OrderBook, quotes: dict[str, Quote]) -> str:
    """
    Returns: The book as a ladder - asks falling towards the spread,
    bids below it - each level backed by a bar the width of everything
    resting at it and ahead of it, and our own quote placed in it.
    """
    bids = _rows(book.bids(LEVELS))
    asks = _rows(book.asks(LEVELS))
    deepest = max(
        [total for _, total in bids] + [total for _, total in asks] + [0.0]
    )

    # Asks are built best price first and shown the other way up, so the
    # spread sits between the two sides' best prices - and a sell quote
    # beyond the levels shown, appended last, lands at the very top.
    ask_rows = "".join(
        reversed(_side_rows(asks, deepest, "ask", quotes.get("SELL")))
    )
    bid_rows = "".join(_side_rows(bids, deepest, "bid", quotes.get("BUY")))

    best_bid, best_ask = book.best_bid(), book.best_ask()
    if best_bid and best_ask:
        spread = best_ask.price - best_bid.price
        mid = (best_ask.price + best_bid.price) / 2
        middle = (
            f'<tr class="jolteon-book-spread"><td colspan="3">'
            f"{mid:,.2f}"
            f"<span>spread {spread:,.2f}"
            f" ({spread / mid * 1e4:,.1f} bps)</span>"
            f"</td></tr>"
        )
    else:
        middle = ""

    return (
        f"<style>{_LADDER_CSS}</style>"
        f'<table class="jolteon-book">'
        f"<thead><tr><th>Price</th><th>Size</th>"
        f"<th>Total</th></tr></thead>"
        f"<tbody>{ask_rows}{middle}{bid_rows}</tbody></table>"
    )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    symbol = read_latest_per_group(db_path, "bbo_feed", "symbol")
    updates = read_table(db_path, "order_book_update_feed")
    book = rebuild(
        updates,
        str(symbol["symbol"].iloc[0]) if not symbol.empty else "",
    )
    if book is None or not book.bbo():
        st.info("No order book recorded yet that this page can read.")
        return

    st.html(ladder_html(book, our_quotes(db_path)))
    st.caption(
        "The outlined row is where our own quote rests - the venue's own"
        " level where it shares a price with one, a line of its own where"
        " it does not. Total is everything resting at a level and ahead"
        " of it."
    )
