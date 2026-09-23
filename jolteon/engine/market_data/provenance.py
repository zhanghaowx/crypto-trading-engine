"""Where the market data a replay consumes came from."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDataProvenance:
    """What a data source can say about the data it hands back.

    `source` names the data, not the run reading it: a recording by its
    path, a venue's history by whatever downloads it. A recording an
    engine is still writing keeps growing, so the path alone does not say
    what was replayed - the interval recorded alongside this is what pins
    that down, and is why two replays of one file are still told apart.

    `source_run_id` is the engine run that recorded the data. It is
    absent when the interval covers more than one run, and when the rows
    carry no run at all.

    `trade_count` is how many market trades the interval holds, which is
    what a later reader compares against how many the replay saw.
    """

    source: str
    source_run_id: str | None = None
    trade_count: int | None = None
