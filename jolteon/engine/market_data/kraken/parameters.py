from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class KrakenFeedParameters(ParameterGroup):
    """
    How the Kraken websocket feed subscribes and how hard it tries to
    stay connected. Read once per connection attempt, so a change here
    reaches the feed when it next reconnects.
    """

    book_depth: int = parameter(
        10,
        minimum=1,
        maximum=1000,
        step=1,
        unit="levels",
        description=(
            "How many levels a side to subscribe to. Everything reading "
            "depth downstream is capped by this."
        ),
    )
    max_retries: int = parameter(
        3,
        minimum=0,
        maximum=100,
        step=1,
        unit="attempts",
        description=(
            "How many times to reconnect before giving up. A connection "
            "that lasted long enough to look healthy resets the count."
        ),
    )
    retry_interval_in_seconds: float = parameter(
        5.0,
        minimum=0.1,
        maximum=300.0,
        step=1.0,
        number_format="%.1f",
        unit="s",
        description="How long to wait between reconnect attempts.",
    )
    min_healthy_connection_seconds: float = parameter(
        60.0,
        minimum=1.0,
        maximum=3600.0,
        step=10.0,
        number_format="%.1f",
        unit="s",
        description=(
            "How long a connection must last to count as healthy and "
            "clear the retry budget."
        ),
    )
