import json
import re
import sqlite3
from unittest import mock

import pandas as pd
from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.dashboard.pages import order_book

    order_book.render()


def _markup(at) -> str:
    """The ladder's markup, without the stylesheet that ships in the same
    block - the CSS names every class the markup does, so counting class
    names across the whole thing counts the rules too."""
    return at.get("html")[-1].body.split("</style>", 1)[-1]


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


def test_a_level_emptied_by_an_update_leaves_the_book(tmp_path):
    """A quantity of zero means the level is gone, and the levels around
    it close up."""
    db_path = _book_db(
        tmp_path,
        "empties.sqlite",
        rows=[(1, [(99.0, 2.0), (98.0, 1.0)], [(101.0, 3.0)], 1, "l2")],
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "99@2|98@1"

    _append(db_path, [(2, [(98.0, 0.0)], [], 0, "l2")])
    _append(db_path, [(3, [(97.5, 4.0)], [], 0, "l2")])
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "99@2|97.5@4"


def test_shows_the_ladder_with_both_sides_and_the_spread(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path)
    at.run()

    assert not at.exception
    body = _markup(at)
    assert "jolteon-book-bid" in body and "jolteon-book-ask" in body
    assert "100.00" in body  # the mid, between 99 and 101
    assert "spread 2.00" in body
    # Total is cumulative away from the spread.
    assert "3.0000" in body and "4.5000" in body


def test_marks_the_venue_level_our_quote_shares_a_price_with(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "quoted.sqlite", quotes=[("BUY", 98.0), ("SELL", 102.0)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    # The venue's own level is outlined rather than given a marker of
    # its own, and keeps its size and running total.
    assert body.count("jolteon-book-resting") == 2
    assert "jolteon-book-alone" not in body


def test_nothing_is_marked_while_we_have_no_quotes_resting(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(tmp_path, "unquoted.sqlite")
    at.run()

    assert not at.exception
    body = _markup(at)
    assert "jolteon-book-resting" not in body
    assert "jolteon-book-alone" not in body


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
    assert "99.50" in body and "100.50" in body


def test_a_quote_between_levels_sits_between_them(tmp_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "between.sqlite", quotes=[("BUY", 98.5)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    prices = re.findall(r'jolteon-book-price">([\d,.]+)<', body)
    # Bids run 99.00, 98.00; ours at 98.50 belongs between them.
    assert prices[-3:] == ["99.00", "98.50", "98.00"]


def test_a_quote_beyond_the_levels_shown_sits_at_its_own_end(tmp_path):
    """Quoting wide enough to fall outside the shown depth would
    otherwise read as having no quote resting at all. The ladder runs in
    price order, so a sell quote out there belongs at the top of it and a
    buy quote at the bottom."""
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = _book_db(
        tmp_path, "wide.sqlite", quotes=[("BUY", 1.0), ("SELL", 500.0)]
    )
    at.run()

    assert not at.exception
    body = _markup(at)
    prices = re.findall(r'jolteon-book-price">([\d,.]+)<', body)
    assert prices[0] == "500.00"
    assert prices[-1] == "1.00"
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

        from jolteon.dashboard.pages.order_book import book_now, ladder_html

        book = book_now(st.session_state["db_path"], "BTC-USD")
        st.write(ladder_html(book, {}).split("</style>", 1)[-1])

    db_path = _book_db(
        tmp_path, "oneside.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l2")]
    )
    at = AppTest.from_function(script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    html = at.markdown[-1].value
    assert "jolteon-book-bid" in html
    assert "jolteon-book-spread" not in html


def _append(db_path, rows) -> None:
    """More updates recorded, as a running engine does."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO order_book_update_feed VALUES "
            "(1700000000, 'BTC-USD', ?, 1, ?, ?, ?, ?, '2026-09-19T18:00:00')",
            [
                (model, sequence, _encode(bids), _encode(asks), snapshot)
                for sequence, bids, asks, snapshot, model in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def carry_script():
    """One refresh of the page, reading whatever the recording holds."""
    import streamlit as st

    from jolteon.dashboard.pages.order_book import book_now

    book = book_now(st.session_state["db_path"], "BTC-USD")
    st.write(
        "|".join(f"{lv.price:g}@{lv.quantity:g}" for lv in book.bids(5))
        if book
        else "none"
    )


def test_a_carried_book_takes_only_the_updates_it_has_not_seen(tmp_path):
    db_path = _book_db(
        tmp_path,
        "carry.sqlite",
        rows=[(1, [(99.0, 2.0)], [(101.0, 3.0)], 1, "l2")],
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "99@2"

    _append(db_path, [(2, [(98.0, 1.0)], [], 0, "l2")])
    at.run()
    _append(db_path, [(3, [(97.0, 4.0)], [], 0, "l2")])
    at.run()

    assert not at.exception
    # Every increment has landed exactly once, in order.
    assert at.markdown[-1].value == "99@2|98@1|97@4"


def test_the_book_is_replayed_from_a_snapshot_older_than_the_table_cache(
    tmp_path,
):
    """Regression test: the replay used to read the updates through the
    general table cache, which keeps only the most recent rows. A session
    soon grows past that, and the snapshot it has to start from is the
    oldest row of all - so the book simply disappeared, saying it could
    not be read."""
    db_path = _book_db(
        tmp_path,
        "long.sqlite",
        rows=[(1, [(99.0, 2.0)], [(101.0, 3.0)], 1, "l2")],
    )
    _append(
        db_path,
        [(i, [(98.0, float(i % 5 + 1))], [], 0, "l2") for i in range(2, 400)],
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    with mock.patch("jolteon.dashboard.data._MAX_CACHED_ROWS", 10):
        at.run()

    assert not at.exception
    assert at.markdown[-1].value.startswith("99@2")


def test_a_fresh_snapshot_throws_the_carried_book_away(tmp_path):
    """A snapshot supersedes everything applied before it, so carrying
    the old book forward would leave levels the venue has dropped."""
    db_path = _book_db(
        tmp_path,
        "resnap.sqlite",
        rows=[(1, [(99.0, 2.0), (98.0, 1.0)], [(101.0, 3.0)], 1, "l2")],
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "99@2|98@1"

    _append(db_path, [(2, [(50.0, 7.0)], [(60.0, 7.0)], 1, "l2")])
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "50@7"


def test_the_carried_book_belongs_to_the_engine_it_was_built_from(tmp_path):
    """Switching symbol switches recording, and the book carried over
    from the last one describes a different market entirely."""
    first = _book_db(
        tmp_path, "btc.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l2")]
    )
    second = _book_db(
        tmp_path, "eth.sqlite", rows=[(1, [(5.0, 1.0)], [], 1, "l2")]
    )

    def script():
        import streamlit as st

        from jolteon.dashboard.pages.order_book import book_now

        one = book_now(st.session_state["first"], "BTC-USD")
        two = book_now(st.session_state["second"], "ETH-USD")
        st.write(f"{one.bids(1)[0].price:g}/{two.bids(1)[0].price:g}")

    at = AppTest.from_function(script)
    at.session_state["first"] = first
    at.session_state["second"] = second
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "99/5"


def test_a_book_with_no_snapshot_to_replay_from_shows_nothing(tmp_path):
    """Updates alone cannot describe a book - there has to be a snapshot
    to apply them to."""
    db_path = _book_db(
        tmp_path, "nosnap.sqlite", rows=[(1, [(99.0, 1.0)], [], 0, "l2")]
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "none"


def test_a_carried_book_is_dropped_when_it_meets_an_unreadable_update(
    tmp_path,
):
    """A recording that starts carrying a book model this page does not
    know cannot be carried forward from the part that it did."""
    db_path = _book_db(
        tmp_path, "l3.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l2")]
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()
    assert at.markdown[-1].value == "99@2"

    _append(db_path, [(2, [(98.0, 1.0)], [], 0, "l3")])
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "none"


def test_a_refresh_that_finds_no_new_updates_keeps_the_book_it_has(tmp_path):
    """Between updates the book is unchanged, and re-reading a recording
    that has not moved must not empty it."""
    db_path = _book_db(
        tmp_path, "quiet.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l2")]
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "99@2"


def test_a_snapshot_of_an_empty_book_leaves_nothing_to_draw(tmp_path):
    """A venue can snapshot a book with nothing resting in it. There is
    a book, it simply has no levels, and the page says as much rather
    than drawing an empty ladder."""
    db_path = _book_db(
        tmp_path, "emptysnap.sqlite", rows=[(1, [], [], 1, "l2")]
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == ""


def test_a_recording_that_opens_in_an_unreadable_model_is_not_guessed_at(
    tmp_path,
):
    """A later book model must not be silently reduced to price levels -
    the page says it cannot read the recording instead."""
    db_path = _book_db(
        tmp_path, "l3snap.sqlite", rows=[(1, [(99.0, 2.0)], [], 1, "l3")]
    )

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert at.markdown[-1].value == "none"


def test_a_refresh_reads_only_what_was_recorded_since_the_last_one(tmp_path):
    """
    The cost of a refresh must not grow with the session. This is the
    property the table cache was standing in for, and it holds here
    without one: the first draw reads from the snapshot, and every
    refresh after reads only the updates added since.
    """
    db_path = _book_db(
        tmp_path,
        "reads.sqlite",
        rows=[(1, [(99.0, 2.0)], [(101.0, 3.0)], 1, "l2")],
    )
    _append(
        db_path,
        [(i, [(98.0, float(i % 5 + 1))], [], 0, "l2") for i in range(2, 500)],
    )

    from jolteon.dashboard.pages import order_book

    read_sizes: list[int] = []
    real = order_book.read_after

    def counting(db, table, rowid):
        frame, at = real(db, table, rowid)
        read_sizes.append(len(frame))
        return frame, at

    at = AppTest.from_function(carry_script)
    at.session_state["db_path"] = db_path
    with mock.patch.object(order_book, "read_after", counting):
        at.run()
        first = list(read_sizes)
        _append(db_path, [(500, [(97.0, 1.0)], [], 0, "l2")])
        at.run()
        refreshed = read_sizes[len(first) :]

    assert not at.exception
    # The first draw replays the session: snapshot plus its 498 updates.
    assert sum(first) == 499
    # The refresh reads the one update recorded since, not the session.
    assert sum(refreshed) == 1
