import pytest

from jolteon.engine.core.health_monitor.health import (
    Health,
    HealthMonitor,
    HealthState,
)


def test_monitor_derives_state_from_every_dependency():
    parameters = Health("parameters")
    market_data = Health("market_data")
    monitor = HealthMonitor()
    monitor.require(parameters)
    monitor.require(market_data)

    assert monitor.state == HealthState.INITIALIZING
    assert not monitor.is_healthy
    parameters.mark_healthy()
    assert monitor.state == HealthState.INITIALIZING
    market_data.mark_healthy()
    assert monitor.state == HealthState.HEALTHY
    assert monitor.is_healthy


def test_critical_takes_precedence_and_recovery_notifies_listeners():
    feed = Health("feed")
    execution = Health("execution")
    monitor = HealthMonitor()
    monitor.require(feed)
    monitor.require(execution)
    changes = []
    monitor.add_listener(changes.append)

    feed.mark_critical()
    execution.mark_healthy()
    feed.mark_healthy()
    feed.mark_healthy()

    assert changes == [
        HealthState.INITIALIZING,
        HealthState.CRITICAL,
        HealthState.HEALTHY,
    ]


def test_action_runs_while_healthy_or_warning_but_not_critical():
    feed = Health("feed")
    monitor = HealthMonitor()
    monitor.require(feed)
    actions = []

    assert not monitor.run_if_can_trade(lambda: actions.append("initializing"))
    feed.mark_healthy()
    assert monitor.run_if_can_trade(lambda: actions.append("healthy"))
    feed.mark_warning()
    assert monitor.state == HealthState.WARNING
    assert monitor.run_if_can_trade(lambda: actions.append("warning"))
    feed.mark_critical()
    assert not monitor.run_if_can_trade(lambda: actions.append("critical"))
    assert actions == ["healthy", "warning"]


def test_dependency_names_identify_one_service():
    monitor = HealthMonitor()
    feed = Health("feed")
    monitor.require(feed)
    monitor.require(feed)

    with pytest.raises(AssertionError, match="already registered"):
        monitor.require(Health("feed"))
