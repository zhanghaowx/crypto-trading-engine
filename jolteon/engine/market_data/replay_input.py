"""Which market data a replay reads."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayInput:
    """What a data source can say about one replay's input.

    `source` names the data, not the run reading it: a recording by its
    path, a venue's history by whatever downloads it. A recording an
    engine is still writing keeps growing, so the path alone does not say
    what was replayed; the interval recorded by `EngineRun` distinguishes
    one requested slice from another.

    `source_run_id` is the engine run that recorded the data. It is
    absent when the interval covers more than one run, and when the rows
    carry no run at all.

    `trade_count` is how many market trades the requested interval holds.
    """

    source: str
    source_run_id: str | None = None
    trade_count: int | None = None
