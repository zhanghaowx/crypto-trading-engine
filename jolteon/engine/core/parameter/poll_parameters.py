from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class ParameterPollParameters(ParameterGroup):
    interval_in_seconds: float = parameter(
        1.0,
        minimum=0.1,
        maximum=60.0,
        step=0.5,
        number_format="%.1f",
        unit="s",
        description=(
            "How long a pushed parameter may take to reach the engine. "
            "Each tick is one trivial query unless something changed."
        ),
    )
