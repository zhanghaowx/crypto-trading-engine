import sqlite3
import time

from jolteon.dashboard.data.heartbeats import recent_heartbeats

NOW = 1_700_000_000.0


def _recording(tmp_path, rows, name="engine.sqlite") -> str:
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE heartbeat "
            "(timestamp REAL, sender TEXT, level INTEGER, message TEXT)"
        )
        conn.executemany(
            "INSERT INTO heartbeat VALUES (?, ?, 1, 'All good')", rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_reads_the_heartbeats_newer_than_the_window_start(tmp_path):
    """The row stamped exactly at the window's start is outside it: the
    window is the last `since_seconds`, and that row is a whole
    `since_seconds` old."""
    db_path = _recording(
        tmp_path,
        [
            (NOW - 400, "MarketMaking"),
            (NOW - 300, "MarketMaking"),
            (NOW - 299, "MarketMaking"),
            (NOW, "MarketMaking"),
        ],
    )

    rows = recent_heartbeats(db_path, since_seconds=300, now=NOW)

    assert list(rows["timestamp"]) == [NOW - 299, NOW]


def test_carries_only_the_time_and_the_sender(tmp_path):
    db_path = _recording(tmp_path, [(NOW, "MarketMaking")])

    rows = recent_heartbeats(db_path, since_seconds=10, now=NOW)

    assert list(rows.columns) == ["timestamp", "sender"]


def test_keeps_every_sender_oldest_first(tmp_path):
    """Recorded out of order and interleaved, as two components writing
    to one table are; read back in the order they happened."""
    db_path = _recording(
        tmp_path,
        [
            (NOW - 5, "MD"),
            (NOW - 20, "MarketMaking"),
            (NOW - 10, "MD"),
            (NOW - 15, "MarketMaking"),
        ],
    )

    rows = recent_heartbeats(db_path, since_seconds=60, now=NOW)

    assert list(zip(rows["timestamp"], rows["sender"])) == [
        (NOW - 20, "MarketMaking"),
        (NOW - 15, "MarketMaking"),
        (NOW - 10, "MD"),
        (NOW - 5, "MD"),
    ]


def test_the_window_ends_at_the_wall_clock_unless_told_otherwise(tmp_path):
    db_path = _recording(
        tmp_path,
        [(time.time() - 1, "MarketMaking"), (NOW, "MarketMaking")],
    )

    rows = recent_heartbeats(db_path, since_seconds=60)

    assert list(rows["sender"]) == ["MarketMaking"]
    assert rows["timestamp"].iloc[0] > NOW


def test_nothing_is_read_from_a_recording_without_heartbeats(
    empty_db_path,
):
    """A recording made before heartbeats were recorded has no history
    to show, and says so with an empty frame rather than an error."""
    assert recent_heartbeats(empty_db_path, since_seconds=300, now=NOW).empty


def test_nothing_is_read_from_a_recording_that_is_not_there(
    missing_db_path,
):
    assert recent_heartbeats(missing_db_path, since_seconds=300, now=NOW).empty
