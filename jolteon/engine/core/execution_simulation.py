"""Resolved settings used to simulate execution during a run."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionSimulationSettings:
    """The resolved settings a run's simulated fills followed from.

    Recorded so a later reader knows which settings its results depend on.
    The latency fields hold nothing while nothing models latency. Zero
    would read as a measured figure and would have every order reaching
    the venue instantly, which is the most optimistic assumption there
    is.
    """

    fee_schedule: str
    maker_rate: float
    taker_rate: float
    queue_model: str
    order_latency_seconds: float | None = None
    cancel_latency_seconds: float | None = None
    market_data_latency_seconds: float | None = None
    random_seed: int | None = None
