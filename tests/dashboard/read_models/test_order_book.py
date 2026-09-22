import json
import sqlite3
from unittest import mock

import pandas as pd
from streamlit.testing.v1 import AppTest


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

    from jolteon.dashboard.read_models.order_book import book_now

    book = book_now(st.session_state["db_path"], "BTC-USD")
    st.write(
        "|".join(f"{lv.price:g}@{lv.quantity:g}" for lv in book.bids(5))
        if book
        else "none"
    )


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
    with mock.patch("jolteon.dashboard.data.sqlite._MAX_CACHED_ROWS", 10):
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

        from jolteon.dashboard.read_models.order_book import book_now

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

    from jolteon.dashboard.read_models import order_book

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
