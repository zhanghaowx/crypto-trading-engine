from dataclasses import dataclass
from datetime import datetime


@dataclass
class AcceptedParameterRevision:
    """One row in a complete parameter snapshot the engine took.

    Every non-secret resolved value is written for a revision, including
    declared defaults and symbol-specific values. Snapshots are never
    rewritten, so resets as well as overrides can be reconstructed at any
    moment of the run.
    """

    INDEX = ("run_id", "revision")

    revision: int
    group_name: str
    field_name: str
    symbol: str
    value: object
    effective_at: datetime
