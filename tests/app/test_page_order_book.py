import json
import sqlite3

import pandas as pd
from streamlit.testing.v1 import AppTest

from jolteon.app.app_pages.order_book import rebuild


def _script():
    from jolteon.app.app_pages import order_book

    order_book.render()


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
            "(timestamp REAL, side TEXT, price REAL, symbol TEXT, "
            "client_order_id TEXT)"
        )
        conn.executemany(
            'INSERT INTO "order" VALUES (1700000000, ?, ?, "BTC-USD", ?)',
            [(side, price, str(i)) for i, (side, price) in enumerate(quotes)],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_a_book_is_rebuilt_from_its_latest_snapshot():
    """Everything before the newest snapshot is superseded by it, so a
    level that was resting only in the older one must be gone."""
    book = rebuild(
        _updates(
            [
                (1, [(90.0, 9.0)], [(110.0, 9.0)], 1, "l2"),
                (2, [(99.0, 2.0)], [(101.0, 3.0)], 1, "l2"),
            ]
        ),
        "BTC-USD",
    )

    assert book is not None
    assert [level.price for level in book.bids(5)] == [99.0]
    assert [level.price for level in book.asks(5)] == [101.0]


def test_increments_after_the_snapshot_are_applied_in_sequence():
    book = rebuild(
        _updates(
            [
                (1, [(99.0, 2.0), (98.0, 1.0)], [(101.0, 3.0)], 1, "l2"),
                # A quantity of zero takes the level away.
                (2, [(98.0, 0.0)], [], 0, "l2"),
                (3, [(97.5, 4.0)], [], 0, "l2"),
            ]
        ),
        "BTC-USD",
    )

    assert book is not None
    assert [level.price for level in book.bids(5)] == [99.0, 97.5]


def test_nothing_is_rebuilt_without_a_snapshot_to_replay_from():
    assert rebuild(_updates([(1, [(99.0, 1.0)], [], 0, "l2")]), "X") is None
    assert rebuild(pd.DataFrame(), "X") is None


def test_a_book_model_this_page_cannot_read_is_not_guessed_at():
    """A later book model must not be silently reduced to price levels -
    the page says it cannot read the recording instead."""
    assert rebuild(_updates([(1, [(99.0, 1.0)], [], 1, "l3")]), "X") is None


def test_shows_the_ladder_with_both_sides_and_the_spread(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path)
    at.run()

    assert not at.exception
    body = at.get("html")[-1].body
    assert "jolteon-book-bid" in body and "jolteon-book-ask" in body
    assert "100.00" in body  # the mid, between 99 and 101
    assert "spread 2.00" in body
    # Total is cumulative away from the spread.
    assert "3.0000" in body and "4.5000" in body


def test_marks_the_level_our_own_quote_rests_at(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "quoted.sqlite", quotes=[("BUY", 98.0), ("SELL", 102.0)]
    )
    at.run()

    assert not at.exception
    body = at.get("html")[-1].body
    # The markup, not the stylesheet that ships in the same block.
    assert body.count('<span class="jolteon-book-ours">') == 2
    assert body.count('jolteon-book-resting"') == 2


def test_nothing_is_marked_while_we_have_no_quotes_resting(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path, "unquoted.sqlite")
    at.run()

    assert not at.exception
    body = at.get("html")[-1].body
    assert '<span class="jolteon-book-ours">' not in body
    assert 'jolteon-book-resting"' not in body


def test_says_so_when_no_book_has_been_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert at.info[0].value.startswith("No order book recorded yet")


def test_warns_when_the_database_is_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning


def test_a_one_sided_book_shows_its_levels_without_a_spread():
    """A venue can leave one side empty for a moment; the ladder still
    draws what is there rather than inventing a spread across nothing."""
    from jolteon.app.app_pages.order_book import ladder_html

    book = rebuild(_updates([(1, [(99.0, 2.0)], [], 1, "l2")]), "BTC-USD")

    assert book is not None
    html = ladder_html(book, {})
    assert 'class="jolteon-book-row jolteon-book-bid"' in html
    assert '<tr class="jolteon-book-spread">' not in html
