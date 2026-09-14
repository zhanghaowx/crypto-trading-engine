from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class BinanceUsFeedParameters(ParameterGroup):
    book_depth: int = parameter(
        1000,
        minimum=100,
        maximum=5000,
        step=100,
        unit="levels",
        description="REST snapshot depth used to synchronize the L2 stream.",
    )
    max_retries: int = parameter(
        3,
        minimum=0,
        maximum=100,
        step=1,
        unit="attempts",
        description="Reconnect attempts before the feed gives up.",
    )
    retry_interval_in_seconds: float = parameter(
        5.0,
        minimum=0.1,
        maximum=300.0,
        step=1.0,
        number_format="%.1f",
        unit="s",
        description="Delay between reconnect attempts.",
    )
    min_healthy_connection_seconds: float = parameter(
        60.0,
        minimum=1.0,
        maximum=3600.0,
        step=10.0,
        number_format="%.1f",
        unit="s",
        description="Connection age that resets the retry budget.",
    )
