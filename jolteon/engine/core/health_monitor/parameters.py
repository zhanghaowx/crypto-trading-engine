from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class HeartbeatParameters(ParameterGroup):
    """
    How often a component says it is alive, and how long the monitor
    waits before deciding one is not. The timeout has to leave room for
    at least one missed beat, or a healthy component reads as a zombie;
    the catalog rejects a pair that does not.
    """

    interval_in_seconds: float = parameter(
        10.0,
        minimum=0.5,
        maximum=600.0,
        step=1.0,
        number_format="%.1f",
        unit="s",
        description="How often each component sends a heartbeat.",
    )
    timeout_in_seconds: float = parameter(
        30.0,
        minimum=1.0,
        maximum=3600.0,
        step=1.0,
        number_format="%.1f",
        unit="s",
        description=(
            "How long a component may stay quiet before the monitor "
            "treats it as a zombie. Matches the threshold the dashboard's "
            "Health page shows a component as down at."
        ),
    )
