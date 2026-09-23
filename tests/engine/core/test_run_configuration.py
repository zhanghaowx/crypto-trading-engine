import sys
from dataclasses import dataclass

from jolteon.engine.core.engine_run import ExecutionMode
from jolteon.engine.core.execution_simulation import (
    ExecutionSimulationSettings,
)
from jolteon.engine.core.health_monitor.health import HealthState
from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.live_parameter_service import (
    LiveParameterService,
)
from jolteon.engine.core.parameter.parameter_service import (
    ALL_SYMBOLS,
    ParameterValues,
    StaticParameterService,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
    parameter,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
)
from jolteon.engine.core.run_configuration import (
    run_environment,
    run_parameters,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)


def _captured(values: ParameterValues) -> dict[tuple[str, str, str], object]:
    return {
        (p.group_name, p.field_name, p.symbol): p.value
        for p in run_parameters(values)
    }


def test_every_declared_parameter_of_every_group_is_captured():
    values = StaticParameterService().values()

    captured = _captured(values)

    for group in parameter_catalog.GROUPS:
        for definition in definitions(group):
            assert (
                group.__name__,
                definition.name,
                ALL_SYMBOLS,
            ) in captured


def test_the_captured_value_is_the_one_the_engine_resolved():
    tuned = MarketMakingParameters(quote_size=0.004)
    values = StaticParameterService(tuned).values()

    captured = _captured(values)

    assert captured[("MarketMakingParameters", "quote_size", ALL_SYMBOLS)] == (
        0.004
    )


def test_capturing_the_snapshot_does_not_count_as_a_component_read():
    """Whether a component has picked a revision up is reported from what
    actually happened at runtime, and recording the snapshot is not a
    component acting on it."""
    values = StaticParameterService().values()

    run_parameters(values)

    assert values.observed == {}


@dataclass(frozen=True)
class Credentialed(ParameterGroup):
    api_key: str = parameter("visible-secret")
    timeout_in_seconds: float = parameter(1.0)


def test_a_field_that_might_hold_a_credential_is_left_out(monkeypatch):
    monkeypatch.setattr(
        parameter_catalog, "GROUPS", (Credentialed,), raising=True
    )
    values = ParameterValues(
        revision=0, defaults={Credentialed: Credentialed()}, by_symbol={}
    )

    captured = _captured(values)

    assert ("Credentialed", "timeout_in_seconds", ALL_SYMBOLS) in captured
    assert ("Credentialed", "api_key", ALL_SYMBOLS) not in captured
    assert "visible-secret" not in [str(value) for value in captured.values()]


def test_a_symbols_own_values_are_captured_beside_the_shared_ones(tmp_path):
    """One store serves every symbol, so a value pushed for one of them
    has to be captured against that symbol rather than replacing the one
    that applies to all of them."""
    db_path = str(tmp_path / "params.sqlite")
    store = ParameterStore(db_path)
    try:
        store.push(
            [
                ParameterChange(
                    "MarketMakingParameters", "quote_size", "BTC/USD", 0.004
                )
            ]
        )
    finally:
        store.close()

    service = LiveParameterService(db_path)
    try:
        service._refresh()
        captured = _captured(service.values())
    finally:
        service.stop()

    assert (
        captured[("MarketMakingParameters", "quote_size", ALL_SYMBOLS)]
        == MarketMakingParameters().quote_size
    )
    assert captured[("MarketMakingParameters", "quote_size", "BTC/USD")] == (
        0.004
    )


def test_the_snapshot_records_the_revision_it_was_taken_at(tmp_path):
    values = ParameterValues(revision=7, defaults={}, by_symbol={})

    assert {p.revision for p in run_parameters(values)} == {7}


class _Simulator:
    execution_mode = ExecutionMode.SIMULATED

    def configure(self, parameters, symbol: str) -> None:
        pass

    def describe_simulation(self, symbol: str) -> ExecutionSimulationSettings:
        return ExecutionSimulationSettings(
            fee_schedule="TestFees",
            maker_rate=0.0,
            taker_rate=0.0002,
            queue_model="QueuePosition",
        )


class _RealVenue:
    execution_mode = ExecutionMode.REAL

    def configure(self, parameters, symbol: str) -> None:
        pass

    def describe_simulation(self, symbol: str) -> None:
        return None


def test_latency_is_recorded_as_unmodelled_rather_than_as_zero():
    """Zero would read as a measured figure, and would be the most
    optimistic assumption available."""
    environment = run_environment(
        values=ParameterValues(revision=0, defaults={}, by_symbol={}),
        execution_service=_Simulator(),
        market_data_feed=_RealVenue(),
        health_state=HealthState.HEALTHY,
        symbol="BTC/USD",
    )
    assumed = environment.execution_simulation

    assert assumed is not None
    assert assumed.order_latency_seconds is None
    assert assumed.cancel_latency_seconds is None
    assert assumed.market_data_latency_seconds is None
    assert assumed.random_seed is None


def test_the_environment_records_the_code_and_the_components():
    values = ParameterValues(revision=3, defaults={}, by_symbol={})

    environment = run_environment(
        values=values,
        execution_service=_Simulator(),
        market_data_feed=_RealVenue(),
        health_state=HealthState.HEALTHY,
        symbol="BTC/USD",
    )

    assert environment.execution_service == "_Simulator"
    assert environment.market_data_feed == "_RealVenue"
    assert environment.parameter_revision == 3
    assert environment.health_state == HealthState.HEALTHY
    assert environment.python_version == sys.version.split()[0]
    assert len(environment.commit) == 40
    assert environment.working_tree_clean in (True, False)
    assert environment.execution_simulation is not None
