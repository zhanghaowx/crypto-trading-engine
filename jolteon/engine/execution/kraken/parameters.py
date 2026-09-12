from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class KrakenExecutionParameters(ParameterGroup):
    poll_interval: float = parameter(
        1.0,
        minimum=0.1,
        maximum=60.0,
        step=0.5,
        number_format="%.1f",
        unit="s",
        description="How often to ask Kraken whether an order has filled.",
    )
    max_retries: int = parameter(
        5,
        minimum=0,
        maximum=100,
        step=1,
        unit="attempts",
        description=(
            "How many times to poll for a fill before giving up on "
            "confirming it."
        ),
    )
    dry_run: bool = parameter(
        False,
        description=(
            "Log orders instead of sending them to the exchange. This "
            "does not make a live session safe on its own."
        ),
    )
