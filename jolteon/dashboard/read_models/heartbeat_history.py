"""A component's recent heartbeats, folded into the intervals it was
meant to send one in.

The recording holds a row per heartbeat; a reader wants to know which of
the last few minutes' intervals went by without one. That is what tells a
component that has been flapping from one that has just gone quiet, and
neither shows in the single latest row the Health page otherwise reads.
"""

import pandas as pd


def history(
    beats: pd.DataFrame,
    sender: str,
    *,
    interval_seconds: float,
    buckets: int,
    now: float,
) -> list[bool]:
    """
    Returns: For each of the last `buckets` intervals of
    `interval_seconds` ending at `now`, oldest first, whether `sender`
    heartbeat inside it.

    An interval runs from its start up to, not including, its end: a
    heartbeat stamped exactly `now` counts in the newest one, and one
    stamped exactly `buckets` intervals ago in none. A heartbeat stamped
    ahead of `now` - a recording clock running ahead of the reader's -
    counts in the newest interval rather than in none.
    """
    if beats.empty:
        return [False] * buckets
    stamps = beats.loc[beats["sender"] == sender, "timestamp"]
    ages = (now - stamps).clip(lower=0.0)
    seen = set((ages // interval_seconds).astype(int).tolist())
    return [
        intervals_ago in seen for intervals_ago in reversed(range(buckets))
    ]
