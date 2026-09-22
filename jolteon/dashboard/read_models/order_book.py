"""The book as the recording leaves it, and our own orders resting in it.

The engine records each normalised book update rather than the book
itself (see RecordedBookUpdate), so the current book is rebuilt here by
replaying from the last snapshot. That keeps the recording narrow - a
book written out level by level widens its table every time the book
moves - and leaves the reader to do the assembling.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from jolteon.dashboard.data.sqlite import (
    last_rowid_where,
    read_after,
    read_latest_per_group,
)
from jolteon.engine.market_data.core.order_book import (
    OrderBook,
    RecordedBookUpdate,
)

FEED = "order_book_update_feed"


@dataclass(frozen=True)
class Quote:
    """One of our own resting orders, as the ladder places it. The size
    is what the order was placed for, and is not always recorded."""

    price: float
    quantity: float | None = None


def _apply(book: OrderBook, rows, symbol: str) -> bool:
    """Applies each recorded update to `book`, saying whether every one of
    them could be read."""
    for row in rows.itertuples():
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
            return False
    return True


def recorded_symbol(db_path: str) -> str:
    """The symbol this recording's book is of, as its latest tick names
    it, and an empty string before the first tick."""
    latest = read_latest_per_group(db_path, "bbo_feed", "symbol")
    return str(latest["symbol"].iloc[0]) if not latest.empty else ""


_CARRIED = "_order_book_carried"


def book_now(db_path: str, symbol: str) -> OrderBook | None:
    """
    Returns: The book as the recording leaves it, or nothing at all when
    no snapshot has been recorded to replay from.

    The book is carried between refreshes and only the updates recorded
    since are applied to it. A book moves constantly, so replaying every
    update since the snapshot each time would be the most expensive thing
    this page does, and all but a handful were applied on the refresh
    before.

    The updates are read straight from the recording rather than through
    the general table cache, which keeps only the most recent rows: a
    session soon grows longer than that, and the snapshot the replay has
    to start from is the oldest row of all.

    The carried book is dropped whenever it cannot be trusted to still
    describe this book: another engine's recording, or a fresh snapshot
    among the new rows - an engine restarting being why there is one.
    """
    carried = st.session_state.get(_CARRIED)
    if carried is not None:
        book, at, was = carried
        if was == (db_path, symbol):
            fresh, now_at = read_after(db_path, FEED, at)
            if fresh.empty:
                return book
            if not fresh["is_snapshot"].astype(bool).any():
                if not _apply(book, fresh, symbol):
                    st.session_state.pop(_CARRIED, None)
                    return None
                st.session_state[_CARRIED] = (book, now_at, was)
                return book

    st.session_state.pop(_CARRIED, None)
    snapshot = last_rowid_where(db_path, FEED, "is_snapshot")
    if snapshot is None:
        return None
    rows, at = read_after(db_path, FEED, snapshot - 1)
    book = OrderBook(symbol)
    if not _apply(book, rows, symbol):
        return None
    st.session_state[_CARRIED] = (book, at, (db_path, symbol))
    return book


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
