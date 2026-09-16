from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class ParameterPollingSettings(ParameterGroup):
    """How often the engine checks for changes to stored parameters."""

    interval_in_seconds: float = parameter(
        1.0,
        minimum=0.1,
        maximum=60.0,
        step=0.5,
        number_format="%.1f",
        unit="s",
        description=(
            "Seconds between checks for parameter changes. Accepted "
            "changes are available the next time a component reads its "
            "parameters."
        ),
    )
