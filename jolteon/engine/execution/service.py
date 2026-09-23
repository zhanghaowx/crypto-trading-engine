"""The execution capability an engine runtime activates."""

from typing import Protocol

from jolteon.engine.core.engine_run import ExecutionMode
from jolteon.engine.core.execution_simulation import (
    ExecutionSimulationSettings,
)
from jolteon.engine.core.parameter.parameter_service import ParameterValues


class IExecutionService(Protocol):
    """An execution service configured before trading signals reach it."""

    execution_mode: ExecutionMode

    def configure(self, parameters: ParameterValues, symbol: str) -> None:
        """Apply one complete, validated parameter revision."""
        ...

    def describe_simulation(
        self, symbol: str
    ) -> ExecutionSimulationSettings | None:
        """Return simulated-execution settings, or none for a real venue."""
        ...
