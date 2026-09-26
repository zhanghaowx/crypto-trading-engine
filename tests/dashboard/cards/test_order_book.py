import json
import re
import sqlite3

import pandas as pd
from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.dashboard.cards import order_book

    order_book.render()


def _markup(at) -> str:
    """The book's markup, without the stylesheet that ships in the same
    block - the CSS names every class the markup does, so counting class
    names across the whole thing counts the rules too."""
    return at.get("html")[-1].body.split("</style>", 1)[-1]


OURS = '<span class="jolteon-book-ours">ours</span>'


def _prices(markup: str, side: str) -> list[str]:
    """One side's prices, top to bottom, whether or not ours is tagged
    in front of them."""
    bids, asks = markup.split(
        '<div class="jolteon-book-side jolteon-book-asks">'
    )
    column = bids if side == "bid" else asks
    return re.findall(
        r'jolteon-book-price">(?:' + re.escape(OURS) + r")?([\d,.]+)<",
        column,
    )


def _css(at) -> str:
    return at.get("html")[-1].body.split("</style>", 1)[0]


def _encode(levels) -> str:
    return json.dumps([[p, q] for p, q in levels], separators=(",", ":"))


def _updates(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model": model,
                "version": 1,
                "sequence": sequence,
                "bids": _encode(bids),
                "asks": _encode(asks),
                "is_snapshot": snapshot,
                "exchange_time": "2026-09-19T18:00:00",
            }
            for sequence, bids, asks, snapshot, model in rows
        ]
    )


def _book_db(tmp_path, name="book.sqlite", *, quotes=(), rows=None) -> str:
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
        )
        conn.execute(
            "INSERT INTO bbo_feed VALUES (1700000000, 'BTC-USD', 99.0, 101.0)"
        )
        conn.execute(
            "CREATE TABLE order_book_update_feed "
            "(timestamp REAL, symbol TEXT, model TEXT, version INTEGER, "
            "sequence INTEGER, bids TEXT, asks TEXT, is_snapshot INTEGER, "
            "exchange_time TEXT)"
        )
        rows = (
            rows
            if rows is not None
            else [
                (
                    1,
                    [(99.0, 2.0), (98.0, 1.0)],
                    [(101.0, 3.0), (102.0, 1.5)],
                    1,
                    "l2",
                )
            ]
        )
        conn.executemany(
            "INSERT INTO order_book_update_feed VALUES "
            "(1700000000, 'BTC-USD', ?, 1, ?, ?, ?, ?, '2026-09-19T18:00:00')",
            [
                (model, sequence, _encode(bids), _encode(asks), snapshot)
                for sequence, bids, asks, snapshot, model in rows
            ],
        )
        conn.execute(
            'CREATE TABLE "order" '
            "(timestamp REAL, side TEXT, price REAL, quantity REAL, "
            "symbol TEXT, client_order_id TEXT)"
        )
        conn.executemany(
            'INSERT INTO "order" VALUES (1700000000, ?, ?, 0.5, "BTC-USD", ?)',
            [(side, price, str(i)) for i, (side, price) in enumerate(quotes)],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_shows_both_sides_best_price_first_and_the_spread_between(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path)
    at.run()

    assert not at.exception
    body = _markup(at)
    assert _prices(body, "bid") == ["99.00", "98.00"]
    assert _prices(body, "ask") == ["101.00", "102.00"]
    assert "<strong>100.00</strong>" in body  # the mid, between 99 and 101
    assert "Spread <b>2.00</b>" in body
    # Total is cumulative away from the spread.
    assert "3.0000" in body and "4.5000" in body


def test_each_side_is_headed_and_sized_in_the_pairs_own_currencies(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path)
    at.run()

    body = _markup(at)
    assert "<h3>Bids <span>· USD</span></h3>" in body
    assert "<h3>Asks <span>· USD</span></h3>" in body
    assert "<th>Size (BTC)</th>" in body
    assert "Spread <b>2.00</b> USD" in body


def test_depth_grows_from_the_middle_of_the_card_outwards(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path)
    at.run()

    body = _markup(at)
    bids, asks = body.split("jolteon-book-asks")
    assert "linear-gradient(to left," in bids
    assert "linear-gradient(to right," in asks


def test_marks_the_venue_level_our_quote_shares_a_price_with(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "quoted.sqlite", quotes=[("BUY", 98.0), ("SELL", 102.0)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    # The venue's own level is tagged rather than given a row of its
    # own, and keeps its size and running total.
    assert body.count("jolteon-book-resting") == 2
    assert "jolteon-book-alone" not in body
    # One tag per marked row, in front of the price so the figures still
    # line up down the column.
    assert body.count(OURS) == 2
    assert f'<td class="jolteon-book-price">{OURS}98.00</td>' in body
    assert f'<td class="jolteon-book-price">{OURS}102.00</td>' in body
    assert _prices(body, "bid") == ["99.00", "98.00"]
    assert _prices(body, "ask") == ["101.00", "102.00"]


def test_our_quote_is_tagged_and_ruled_rather_than_boxed(tmp_path):
    """The quote is the least important thing on the page to read, so
    it gets a small tag and a rule down the row's leading edge - not an
    outline, and not a bold row."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "tagged.sqlite", quotes=[("BUY", 98.0)]
    )
    at.run()

    css = _css(at)
    assert (
        ".jolteon-book-resting td:first-child {\n"
        "  box-shadow: inset 3px 0 0 var(--ink);" in css
    )
    assert "text-transform: uppercase" in css
    assert "outline:" not in css
    assert ".jolteon-book-resting {" not in css


def test_nothing_is_marked_while_we_have_no_quotes_resting(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path, "unquoted.sqlite")
    at.run()

    assert not at.exception
    body = _markup(at)
    assert "jolteon-book-resting" not in body
    assert "jolteon-book-alone" not in body
    assert OURS not in body


def test_says_so_when_no_book_has_been_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.info
    assert at.caption[0].value.startswith("No order book recorded yet")


def test_warns_when_the_database_is_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning


def test_a_quote_inside_the_spread_takes_a_row_of_its_own(tmp_path):
    """Regression test: the diamond used to need our price to equal a
    venue level exactly. A market maker quoting inside the touch sits in
    the gap where the book has no level at all, so nothing was marked -
    and in paper trading, where our orders never reach the venue's book,
    that was every quote."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "inside.sqlite", quotes=[("BUY", 99.5), ("SELL", 100.5)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    assert body.count("jolteon-book-alone") == 2
    assert body.count(OURS) == 2
    assert f'<td class="jolteon-book-price">{OURS}99.50</td>' in body
    assert f'<td class="jolteon-book-price">{OURS}100.50</td>' in body


def test_a_quote_between_levels_sits_between_them(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "between.sqlite", quotes=[("BUY", 98.5)]
    )
    at.run()

    assert not at.exception
    # Bids run 99.00, 98.00; ours at 98.50 belongs between them.
    assert _prices(_markup(at), "bid") == ["99.00", "98.50", "98.00"]


def test_a_quote_beyond_the_levels_shown_sits_at_its_own_end(tmp_path):
    """Quoting wide enough to fall outside the shown depth would
    otherwise read as having no quote resting at all. Each side runs in
    price order away from the spread, so a quote out there belongs at
    the bottom of its own column."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "wide.sqlite", quotes=[("BUY", 1.0), ("SELL", 500.0)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    assert _prices(body, "ask")[-1] == "500.00"
    assert _prices(body, "bid")[-1] == "1.00"
    assert body.count("jolteon-book-alone") == 2


def test_a_price_that_only_prints_the_same_still_marks_its_level(tmp_path):
    """Our order's price and the venue's level reach the recording by
    different routes, so they are compared with a tolerance."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "nearly.sqlite", quotes=[("BUY", 99.0 + 1e-13)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    assert "jolteon-book-alone" not in body
    assert body.count("jolteon-book-resting") == 1


def test_a_one_sided_book_shows_its_levels_without_a_spread(tmp_path):
    """A venue can leave one side empty for a moment; the ladder still
    draws what is there rather than inventing a spread across nothing."""

    def script():
        import streamlit as st

        from jolteon.dashboard.cards.order_book import book_html, book_now

        book = book_now(st.session_state["db_path"], "BTC-USD")
        st.write(book_html(book, {}, "BTC-USD").split("</style>", 1)[-1])

    db_path = _book_db(
        tmp_path, "oneside.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l2")]
    )
    at = AppTest.from_function(script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    html = at.markdown[-1].value
    assert "jolteon-book-bid" in html
    assert "jolteon-book-mid" not in html


def test_a_symbol_that_is_not_a_pair_gets_no_currency_labels(tmp_path):
    def script():
        import streamlit as st

        from jolteon.dashboard.cards.order_book import book_html, book_now

        book = book_now(st.session_state["db_path"], "BTC-USD")
        st.write(book_html(book, {}, "").split("</style>", 1)[-1])

    at = AppTest.from_function(script)
    at.session_state["db_path"] = _book_db(tmp_path, "unpaired.sqlite")
    at.run()

    assert not at.exception
    html = at.markdown[-1].value
    assert "<h3>Bids</h3>" in html
    assert "<th>Size</th>" in html
    assert "Spread <b>2.00</b> · " in html
