import logging
import threading

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.health_monitor.heartbeat import (
    Heartbeater,
    HeartbeatLevel,
)
from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.parameter_applied import (
    REJECTED,
    TAKEN,
    UNKNOWN,
    ParameterApplied,
    applied_key,
)
from jolteon.engine.core.parameter.parameter_service import (
    ALL_SYMBOLS,
    IParameterService,
    ParameterValues,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterOverride,
    ParameterStore,
)
from jolteon.engine.core.parameter.poll_parameters import (
    ParameterPollParameters,
)

_REJECTED_PUSH = "Rejected a pushed parameter"


def _identity(override: ParameterOverride) -> tuple[str, str, str]:
    return (override.group_name, override.field_name, override.symbol)


class StoredParameterService(IParameterService, Heartbeater):
    """
    Parameters that a dashboard can change while the engine is running.

    A thread of its own watches the store and rebuilds every group when
    something has been pushed, so the engine's own threads never touch a
    file to read a tunable: they read values this thread already built.

    Deliberately not a SignalSubscriber, and deliberately free of any
    property that reads the store - ApplicationBase is walked attribute
    by attribute to find subscribers, and anything reachable that way
    would be touched during wiring.
    """

    def __init__(self, database_name: str, name: str = ""):
        # interval_in_seconds=0 disables Heartbeater's own asyncio loop:
        # this component's real work runs on a thread, and its heartbeat
        # goes out from that loop so a stall there stops the heartbeats.
        Heartbeater.__init__(
            self, name or type(self).__name__, interval_in_seconds=0
        )
        self._store = ParameterStore(database_name)
        self._values = _build(revision=0, overrides=[], previous=None)
        self._data_version: int | None = None
        self._applied_overrides: list[ParameterOverride] = []
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._emitted: dict[str, tuple] = {}
        self._stored: dict[str, ParameterOverride] = {}
        self._rejected: dict[str, tuple[str, str]] = {}
        # Created here rather than in the polling loop: SignalRecorder
        # scans the namespace once, when recording starts, so a signal
        # that appears later is never persisted.
        self.parameter_applied_event = signal("parameter_applied")

    def values(self) -> ParameterValues:
        return self._values

    def start(self) -> None:
        if self._thread is not None:
            return
        self._refresh()
        self._thread = threading.Thread(
            name="Parameters", target=self._poll, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        # The store holds one read-only connection open for as long as it
        # is polled, and Windows refuses to remove a file still open.
        self._store.close()

    def _poll(self) -> None:
        while not self._stopping.is_set():
            try:
                self._refresh()
            except Exception as error:
                logging.error(f"Could not refresh parameters: {error}")
            self.send_heartbeat()
            interval = self._values.get(
                ParameterPollParameters
            ).interval_in_seconds
            self._stopping.wait(interval)

    def _refresh(self) -> None:
        version = self._store.data_version()
        if version is not None and version == self._data_version:
            self._emit()
            return
        self._data_version = version

        # data_version is only an optimisation, and reports nothing at
        # all while the store does not exist yet. What the rows say is
        # what decides a rebuild, so an engine running without a
        # dashboard does not advance its revision on every tick.
        overrides = sorted(self._store.read(), key=_identity)
        if overrides == self._applied_overrides:
            self._emit()
            return
        self._applied_overrides = overrides

        rebuilt, rejected = _build_checked(
            revision=self._values.revision + 1,
            overrides=overrides,
            previous=self._values,
        )
        if rebuilt is not None:
            self._values = rebuilt
            self.remove_issue(_REJECTED_PUSH)
        else:
            self.add_issue(HeartbeatLevel.WARN, _REJECTED_PUSH)

        self._emit(overrides, rejected)

    def _emit(
        self,
        overrides: list[ParameterOverride] | None = None,
        rejected: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """
        Publishes any applied state that has moved since it was last
        published, which after a push means a field flipping from stored
        to read as each component next looks at its group.

        Only pushed fields are reported. A field left at its declared
        default has nothing to say about whether a push arrived.
        """
        if overrides is not None:
            self._stored = {
                applied_key(o.group_name, o.field_name, o.symbol): o
                for o in overrides
            }
            self._rejected = rejected or {}

        known = parameter_catalog.group_by_name()
        for key, override in self._stored.items():
            group = known.get(override.group_name)
            observed = (
                self._values.observed.get(group, 0) if group is not None else 0
            )
            status, reason = self._rejected.get(key, (TAKEN, ""))

            state = (self._values.revision, observed, status, reason)
            if self._emitted.get(key) == state:
                continue
            self._emitted[key] = state

            self.parameter_applied_event.send(
                self.parameter_applied_event,
                parameter_applied=ParameterApplied(
                    key=key,
                    group_name=override.group_name,
                    field_name=override.field_name,
                    symbol=override.symbol,
                    stored_value=str(override.value),
                    revision=self._values.revision,
                    observed_revision=observed,
                    status=status,
                    reason=reason,
                ),
            )


def _build_checked(
    revision: int,
    overrides: list[ParameterOverride],
    previous: ParameterValues,
) -> tuple[ParameterValues | None, dict[str, tuple[str, str]]]:
    """
    Returns: The rebuilt values, or None when the push was refused,
    alongside a status and a reason for every field refused.

    Refusing keeps the engine on the values it was already running, so a
    bad push can never stop it quoting.
    """
    rejected: dict[str, tuple[str, str]] = {}
    known = parameter_catalog.group_by_name()
    usable = []
    for override in overrides:
        group = known.get(override.group_name)
        key = applied_key(
            override.group_name, override.field_name, override.symbol
        )
        if group is None or override.field_name not in {
            d.name for d in definitions(group)
        }:
            rejected[key] = (UNKNOWN, "No such parameter in this engine")
            continue
        usable.append(override)

    try:
        rebuilt = _build(revision, usable, previous)
    except (TypeError, ValueError) as error:
        for override in usable:
            key = applied_key(
                override.group_name, override.field_name, override.symbol
            )
            rejected[key] = (REJECTED, str(error))
        return None, rejected

    problems = parameter_catalog.validate(rebuilt)
    for problem in problems:
        key = applied_key(problem.group_name, problem.field_name, ALL_SYMBOLS)
        rejected[key] = (REJECTED, problem.message)
    if problems:
        return None, rejected

    return rebuilt, rejected


def _build(
    revision: int,
    overrides: list[ParameterOverride],
    previous: ParameterValues | None,
) -> ParameterValues:
    by_group: dict[str, dict[str, object]] = {}
    by_symbol_fields: dict[str, dict[str, dict[str, object]]] = {}
    for override in overrides:
        target = (
            by_group
            if override.symbol == ALL_SYMBOLS
            else by_symbol_fields.setdefault(override.symbol, {})
        )
        target.setdefault(override.group_name, {})[override.field_name] = (
            override.value
        )

    defaults = {
        group: _construct(group, by_group.get(group.__name__, {}))
        for group in parameter_catalog.GROUPS
    }
    # A symbol's map has to hold every group, not just the overridden
    # ones, so a lookup that falls to it does not miss the rest.
    by_symbol = {
        symbol: {
            group: (
                _construct(group, overridden)
                if (overridden := fields.get(group.__name__))
                else defaults[group]
            )
            for group in parameter_catalog.GROUPS
        }
        for symbol, fields in by_symbol_fields.items()
    }
    return ParameterValues(
        revision=revision,
        defaults=defaults,
        by_symbol=by_symbol,
        observed=previous.observed if previous else None,
    )


def _construct(
    group: type[ParameterGroup], values: dict[str, object]
) -> ParameterGroup:
    # Values arrive as JSON scalars, so an int field pushed as 10 must
    # not come back a float and silently change how it is used.
    coerced = {
        d.name: d.value_type(values[d.name])
        for d in definitions(group)
        if d.name in values
    }
    return group(**coerced)  # type: ignore[call-arg]
