from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class BookFeatureParameters(ParameterGroup):
    depth: int = parameter(
        10,
        minimum=1,
        maximum=100,
        step=1,
        unit="levels",
        description=(
            "How many levels a side the recorded book features cover. "
            "The feed's subscription depth caps what is available."
        ),
    )
