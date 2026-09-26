"""Explicit complete parameter revisions used by recorded-data runs."""

import math
from typing import cast

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.health_monitor.parameters import HeartbeatParameters
from jolteon.engine.core.parameter.accepted_parameter_revision import (
    AcceptedParameterRevision,
)
from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    ParameterValues,
)
from jolteon.engine.core.parameter.parameter_specification import definitions
from jolteon.engine.core.time.time_manager import time_manager


def resolved_parameters(scopes: dict, revision: int = 0) -> ParameterValues:
    if not isinstance(scopes, dict) or "" not in scopes:
        raise ValueError("Parameters require a complete default scope ''")
    groups = {group.__name__: group for group in GROUPS}
    resolved = {}
    for symbol, settings in scopes.items():
        if symbol not in ("", "BTC/USD"):
            raise ValueError(f"Unsupported parameter scope: {symbol}")
        if not isinstance(settings, dict) or set(settings) != set(groups):
            raise ValueError("Every parameter scope must contain all groups")
        values = {}
        for name, group in groups.items():
            fields = {
                definition.name: definition
                for definition in definitions(group)
            }
            supplied = settings[name]
            if not isinstance(supplied, dict) or set(supplied) != set(fields):
                raise ValueError(f"Incomplete or unknown fields in {name}")
            for key, definition in fields.items():
                value = supplied[key]
                valid = type(value) in (int, float) and math.isfinite(value)
                if definition.value_type is bool:
                    valid = type(value) is bool
                elif definition.value_type is int:
                    valid = type(value) is int
                if not valid:
                    raise ValueError(f"Invalid parameter type: {name}.{key}")
                if (
                    definition.minimum is not None
                    and value < definition.minimum
                ) or (
                    definition.maximum is not None
                    and value > definition.maximum
                ):
                    raise ValueError(f"Parameter out of bounds: {name}.{key}")
            values[group] = group(**supplied)
        heartbeat = cast(HeartbeatParameters, values[HeartbeatParameters])
        if heartbeat.timeout_in_seconds <= heartbeat.interval_in_seconds:
            raise ValueError("Heartbeat timeout must exceed its interval")
        resolved[symbol] = values
    return ParameterValues(revision, resolved.pop(""), resolved)


class ReplayParameters(IParameterService):
    def __init__(self, scopes: dict):
        self._values = resolved_parameters(scopes)
        self._revision_event = signal("accepted_parameter_revision")

    def values(self) -> ParameterValues:
        return self._values

    def replace(self, scopes: dict, revision: int) -> None:
        self._values = resolved_parameters(scopes, revision)
        for symbol, groups in scopes.items():
            for group, fields in groups.items():
                for field, value in fields.items():
                    self._revision_event.send(
                        self._revision_event,
                        revision=AcceptedParameterRevision(
                            revision,
                            group,
                            field,
                            symbol,
                            value,
                            time_manager().now(),
                        ),
                    )

    def start(self) -> None:
        self.mark_parameters_healthy()
