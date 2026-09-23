"""What an engine run was configured with when it started.

Recorded into the run's own recording, so a run that finished months ago
still answers what it was running - rather than being reconstructed from
a parameter store the dashboard has changed many times since.
"""

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jolteon.engine.core.code_version import commit_sha, working_tree_is_clean
from jolteon.engine.core.execution_simulation import (
    ExecutionSimulationSettings,
)
from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.parameter_service import (
    ALL_SYMBOLS,
    ParameterValues,
)
from jolteon.engine.core.parameter.parameter_specification import definitions
from jolteon.engine.core.secrets import looks_secret

if TYPE_CHECKING:
    from jolteon.engine.execution.service import IExecutionService


@dataclass
class RunParameter:
    """One resolved parameter value as a run started.

    One row per field per scope rather than one wide row, so a parameter
    added or dropped later changes nothing about how an earlier run's
    configuration is read back.
    """

    INDEX = ("run_id",)

    group_name: str
    field_name: str
    symbol: str
    value: object
    revision: int


@dataclass
class RunEnvironment:
    """Everything but the parameters that decided what a run did."""

    INDEX = ("run_id",)

    commit: str
    working_tree_clean: bool | None
    python_version: str
    execution_service: str
    market_data_feed: str
    parameter_revision: int
    health_state: str
    execution_simulation: ExecutionSimulationSettings | None = None


def run_parameters(values: ParameterValues) -> list[RunParameter]:
    """
    Returns: Every parameter the engine resolved, in each scope these
    values carry - the values that apply to every symbol, and then each
    symbol carrying values of its own.

    Read without counting as a read, so capturing the snapshot does not
    make it look as though a component had picked the revision up.

    A field whose name suggests a credential is left out: a recording is
    read by the dashboard and exported from there, and a secret written
    into one cannot be taken back.
    """
    return [
        RunParameter(
            group_name=group.__name__,
            field_name=definition.name,
            symbol=symbol,
            value=getattr(current, definition.name),
            revision=values.revision,
        )
        for symbol in (ALL_SYMBOLS, *values.symbols)
        for group in parameter_catalog.GROUPS
        for current in (values.peek(group, symbol),)
        for definition in definitions(group)
        if not looks_secret(definition.name)
    ]


def run_environment(
    values: ParameterValues,
    execution_service: "IExecutionService | None",
    market_data_feed: object,
    health_state: str,
    symbol: str,
) -> RunEnvironment:
    """
    Returns: The code, the components and the simulator assumptions the
    run is about to trade under.
    """
    return RunEnvironment(
        commit=commit_sha(),
        working_tree_clean=working_tree_is_clean(),
        python_version=sys.version.split()[0],
        execution_service=type(execution_service).__name__,
        market_data_feed=type(market_data_feed).__name__,
        parameter_revision=values.revision,
        health_state=health_state,
        execution_simulation=(
            None
            if execution_service is None
            else execution_service.describe_simulation(symbol)
        ),
    )
