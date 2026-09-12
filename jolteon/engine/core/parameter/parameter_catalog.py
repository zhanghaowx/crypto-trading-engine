from dataclasses import dataclass

from jolteon.engine.core.health_monitor.parameters import HeartbeatParameters
from jolteon.engine.core.logging.parameters import LoggingParameters
from jolteon.engine.core.parameter.parameter_service import (
    ParameterValues,
    assert_within_bounds,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
)
from jolteon.engine.core.parameter.poll_parameters import (
    ParameterPollParameters,
)
from jolteon.engine.core.retry import RetryParameters
from jolteon.engine.core.sqlite_writer import SqliteWriterParameters
from jolteon.engine.execution.kraken.fee_schedule import KrakenFeeSchedule
from jolteon.engine.execution.kraken.parameters import (
    KrakenExecutionParameters,
)
from jolteon.engine.market_data.kraken.parameters import KrakenFeedParameters
from jolteon.engine.market_data.parameters import BookFeatureParameters
from jolteon.engine.strategy.market_making.fair_value.parameters import (
    AdjustedFairPriceParameters,
    InventoryAdjustmentParameters,
    MicropriceParameters,
    MomentumParameters,
    OrderFlowImbalanceParameters,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
    QuoteOffsetParameters,
)

# Every group the engine reads and the dashboard offers for editing.
# A group listed here needs nothing else to appear on the Parameters
# page: it is rendered from what its fields declare.
#
# Each import above must stay cheap. The dashboard imports this to draw
# its editor, and it runs in a process with no market data feed or
# exchange client to load.
GROUPS: tuple[type[ParameterGroup], ...] = (
    MarketMakingParameters,
    QuoteOffsetParameters,
    AdjustedFairPriceParameters,
    MomentumParameters,
    OrderFlowImbalanceParameters,
    InventoryAdjustmentParameters,
    MicropriceParameters,
    KrakenFeedParameters,
    KrakenExecutionParameters,
    KrakenFeeSchedule,
    BookFeatureParameters,
    HeartbeatParameters,
    RetryParameters,
    SqliteWriterParameters,
    LoggingParameters,
    ParameterPollParameters,
)


@dataclass(frozen=True)
class ParameterProblem:
    group_name: str
    field_name: str
    message: str


def group_by_name() -> dict[str, type[ParameterGroup]]:
    return {group.__name__: group for group in GROUPS}


def validate(values: ParameterValues) -> list[ParameterProblem]:
    """
    Returns: A problem for every field whose value breaks its own
    declared bounds.

    Reports all of them rather than stopping at the first, so one push
    gets one complete answer.
    """
    problems = list(_cross_group_problems(values))
    for group in GROUPS:
        current = values.peek(group)
        for definition in definitions(group):
            try:
                assert_within_bounds(
                    group, definition, getattr(current, definition.name)
                )
            except AssertionError as error:
                problems.append(
                    ParameterProblem(
                        group_name=group.__name__,
                        field_name=definition.name,
                        message=str(error),
                    )
                )
    return problems


def _cross_group_problems(values: ParameterValues):
    """
    Constraints that no single field can state, because they are about
    how two of them sit together.
    """
    heartbeat = values.peek(HeartbeatParameters)
    if heartbeat.timeout_in_seconds <= heartbeat.interval_in_seconds:
        yield ParameterProblem(
            group_name="HeartbeatParameters",
            field_name="timeout_in_seconds",
            message=(
                "timeout_in_seconds must exceed interval_in_seconds, or a "
                "component is a zombie before its next heartbeat is due"
            ),
        )
