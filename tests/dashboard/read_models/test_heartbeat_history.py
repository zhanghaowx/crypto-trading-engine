import pandas as pd

from jolteon.dashboard.read_models.heartbeat_history import history

NOW = 1_700_000_000.0
INTERVAL = 10.0


def _beats(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["timestamp", "sender"])


def _every_interval(sender: str, *, skipping=()) -> list[tuple]:
    """A sender heartbeating once every interval over the whole window,
    a moment after each interval starts, except in the intervals named
    in `skipping` (counted back from the newest, zero being the one
    ending at `NOW`)."""
    return [
        (NOW - (intervals_ago + 1) * INTERVAL + 1, sender)
        for intervals_ago in range(4)
        if intervals_ago not in skipping
    ]


def test_a_sender_that_never_missed_reports_every_interval():
    beats = _beats(*_every_interval("MarketMaking"))

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert reported == [True, True, True, True]


def test_a_missed_interval_is_left_hollow_in_its_own_place():
    """Oldest first: an interval missed two before the newest sits two
    from the end of the row."""
    beats = _beats(*_every_interval("MarketMaking", skipping=(2,)))

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert reported == [True, False, True, True]


def test_an_interval_runs_up_to_but_not_including_its_end():
    """A heartbeat stamped exactly `NOW` is in the newest interval and one
    stamped exactly a window ago is in none; one stamped exactly an
    interval ago belongs to the interval before the newest, whose end it
    sits on."""
    beats = _beats(
        (NOW, "MarketMaking"),
        (NOW - INTERVAL, "MarketMaking"),
        (NOW - 4 * INTERVAL, "MarketMaking"),
    )

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert reported == [False, False, True, True]


def test_a_heartbeat_stamped_ahead_of_now_counts_as_the_newest():
    beats = _beats((NOW + 2, "MarketMaking"))

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert reported == [False, False, False, True]


def test_a_sender_with_no_heartbeats_reported_nothing():
    beats = _beats(*_every_interval("MD"))

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert reported == [False, False, False, False]


def test_no_heartbeats_at_all_is_a_row_of_nothing_reported():
    """A recording without the table hands over a frame with no columns,
    not just no rows."""
    reported = history(
        pd.DataFrame(),
        "MarketMaking",
        interval_seconds=INTERVAL,
        buckets=3,
        now=NOW,
    )

    assert reported == [False, False, False]


def test_each_sender_reads_only_its_own_heartbeats():
    beats = _beats(
        *_every_interval("MD", skipping=(0,)),
        *_every_interval("MarketMaking", skipping=(3,)),
    )

    market_data = history(
        beats, "MD", interval_seconds=INTERVAL, buckets=4, now=NOW
    )
    market_making = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=4, now=NOW
    )

    assert market_data == [True, True, True, False]
    assert market_making == [False, True, True, True]


def test_two_heartbeats_in_one_interval_report_it_once():
    beats = _beats((NOW - 1, "MarketMaking"), (NOW - 2, "MarketMaking"))

    reported = history(
        beats, "MarketMaking", interval_seconds=INTERVAL, buckets=2, now=NOW
    )

    assert reported == [False, True]
