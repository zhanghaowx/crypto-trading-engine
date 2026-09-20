"""The book as it stands, and where our own quotes sit in it.

The engine records each normalised book update rather than the book
itself (see RecordedBookUpdate), so the current book is rebuilt here by
replaying from the last snapshot. That keeps the recording narrow - a
book written out level by level widens its table every time the book
moves - and leaves the dashboard to do the assembling.
"""

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


def _quote_prices(db_path: str) -> dict[str, float]:
    """The price of our own latest order on each side, which is what the
    ladder marks so a reader can see where we are resting."""
    quotes = read_latest_per_group(db_path, "order", "side")
    if quotes.empty or "price" not in quotes.columns:
        return {}
    return {
        str(row.side): float(row.price)
        for row in quotes.itertuples()
        if pd.notna(row.price)
    }


def _ladder_row(
    level: PriceLevel,
    cumulative: float,
    deepest: float,
    side: str,
    ours: bool,
) -> str:
    fill = (cumulative / deepest * 100) if deepest else 0.0
    mark = '<span class="jolteon-book-ours">◆</span>' if ours else ""
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
        f'<td class="jolteon-book-mark">{mark}</td>'
        f'<td class="jolteon-book-price">{level.price:,.2f}</td>'
        f"<td>{level.quantity:,.4f}</td>"
        f"<td>{cumulative:,.4f}</td>"
        f"</tr>"
    )


def ladder_html(book: OrderBook, quotes: dict[str, float]) -> str:
    """
    Returns: The book as a ladder - asks falling towards the spread,
    bids below it - each level backed by a bar the width of everything
    resting at it and ahead of it, and our own resting price marked.
    """
    bids = _rows(book.bids(LEVELS))
    asks = _rows(book.asks(LEVELS))
    deepest = max(
        [total for _, total in bids] + [total for _, total in asks] + [0.0]
    )

    ask_rows = "".join(
        _ladder_row(
            level, total, deepest, "ask", level.price == quotes.get("SELL")
        )
        for level, total in reversed(asks)
    )
    bid_rows = "".join(
        _ladder_row(
            level, total, deepest, "bid", level.price == quotes.get("BUY")
        )
        for level, total in bids
    )

    best_bid, best_ask = book.best_bid(), book.best_ask()
    if best_bid and best_ask:
        spread = best_ask.price - best_bid.price
        mid = (best_ask.price + best_bid.price) / 2
        middle = (
            f'<tr class="jolteon-book-spread"><td colspan="4">'
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
        f"<thead><tr><th></th><th>Price</th><th>Size</th>"
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

    st.html(ladder_html(book, _quote_prices(db_path)))
    st.caption(
        "The diamond marks the level our own quote is resting at. Total is"
        " everything resting at a level and ahead of it."
    )
