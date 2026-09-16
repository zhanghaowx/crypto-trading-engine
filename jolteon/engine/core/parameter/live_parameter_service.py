import logging
import threading

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.health_monitor.heartbeat import (
    Heartbeater,
)
from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.parameter_change_result import (
    REJECTED,
    TAKEN,
    UNKNOWN,
    ParameterChangeResult,
    change_key,
)
from jolteon.engine.core.parameter.parameter_group_revision import (
    ParameterGroupRevision,
)
from jolteon.engine.core.parameter.parameter_polling_settings import (
    ParameterPollingSettings,
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
    ParameterChange,
    ParameterStore,
)

_REJECTED_PUSH = "Rejected a pushed parameter"


def _identity(change: ParameterChange) -> tuple[str, str, str]:
    return (change.group_name, change.field_name, change.symbol)


class LiveParameterService(IParameterService, Heartbeater):
    """
    Refresh engine parameters from the store while the engine is running.

    On start, load stored changes, then poll for changes on a background
    thread. Validate each new snapshot before replacing the current one;
    if validation fails, keep the previous values. Components read the
    snapshot from memory without accessing the database.

    Publish change results, group revisions, and a heartbeat from the
    polling thread.
    Components see accepted changes when they next read their parameters.
    """

    def __init__(
        self,
        database_name: str,
        name: str = "",
        health_monitor: HealthMonitor | None = None,
    ):
        # interval_in_seconds=0 disables Heartbeater's own asyncio loop:
        # this component's real work runs on a thread, and its heartbeat
        # goes out from that loop so a stall there stops the heartbeats.
        Heartbeater.__init__(
            self,
            name or "parameters",
            interval_in_seconds=0,
            health_monitor=health_monitor,
        )
        self._store = ParameterStore(database_name)
        self._values = _build(revision=0, changes=[], previous=None)
        self._data_version: int | None = None
        self._last_changes: list[ParameterChange] = []
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._emitted_results: dict[str, ParameterChangeResult] = {}
        self._emitted_revisions: dict[str, ParameterGroupRevision] = {}
        self._stored: dict[str, ParameterChange] = {}
        self._rejected: dict[str, tuple[str, str]] = {}
        # Created here rather than in the polling loop: SignalRecorder
        # scans the namespace once, when recording starts, so a signal
        # that appears later is never persisted.
        self.parameter_change_result_event = signal("parameter_change_result")
        self.parameter_group_revision_event = signal(
            "parameter_group_revision"
        )

    def values(self) -> ParameterValues:
        return self._values

    def start(self) -> None:
        if self._thread is not None:
            return
        self._refresh()
        self.mark_healthy()
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
                self.mark_critical()
                logging.error(f"Could not refresh parameters: {error}")
            else:
                self.mark_healthy()
            self.send_heartbeat()
            interval = self._values.get(
                ParameterPollingSettings
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
        changes = sorted(self._store.read(), key=_identity)
        if changes == self._last_changes:
            self._emit()
            return
        self._last_changes = changes

        rebuilt, rejected = _build_checked(
            revision=self._values.revision + 1,
            changes=changes,
            previous=self._values,
        )
        if rebuilt is not None:
            self._values = rebuilt
            self.remove_issue(_REJECTED_PUSH)
        else:
            self.add_issue(HealthState.WARNING, _REJECTED_PUSH)

        self._emit(changes, rejected)

    def _emit(
        self,
        changes: list[ParameterChange] | None = None,
        rejected: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """Publish changed field results and group revisions independently."""
        if changes is not None:
            self._stored = {
                change_key(c.group_name, c.field_name, c.symbol): c
                for c in changes
            }
            self._rejected = rejected or {}
            self._emitted_results = {
                key: result
                for key, result in self._emitted_results.items()
                if key in self._stored
            }

        for key, change in self._stored.items():
            status, reason = self._rejected.get(key, (TAKEN, ""))
            result = ParameterChangeResult(
                key=key,
                group_name=change.group_name,
                field_name=change.field_name,
                symbol=change.symbol,
                stored_value=str(change.value),
                status=status,
                reason=reason,
            )
            if self._emitted_results.get(key) == result:
                continue
            self._emitted_results[key] = result
            self.parameter_change_result_event.send(
                self.parameter_change_result_event,
                parameter_change_result=result,
            )

        for group in parameter_catalog.GROUPS:
            revision = ParameterGroupRevision(
                group_name=group.__name__,
                current_revision=self._values.revision,
                last_read_revision=self._values.observed.get(group),
            )
            if self._emitted_revisions.get(group.__name__) == revision:
                continue
            self._emitted_revisions[group.__name__] = revision
            self.parameter_group_revision_event.send(
                self.parameter_group_revision_event,
                parameter_group_revision=revision,
            )


def _build_checked(
    revision: int,
    changes: list[ParameterChange],
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
    for change in changes:
        group = known.get(change.group_name)
        key = change_key(change.group_name, change.field_name, change.symbol)
        if group is None or change.field_name not in {
            d.name for d in definitions(group)
        }:
            rejected[key] = (UNKNOWN, "No such parameter in this engine")
            continue
        usable.append(change)

    try:
        rebuilt = _build(revision, usable, previous)
    except (TypeError, ValueError) as error:
        for change in usable:
            key = change_key(
                change.group_name, change.field_name, change.symbol
            )
            rejected[key] = (REJECTED, str(error))
        return None, rejected

    problems = parameter_catalog.validate(rebuilt)
    for problem in problems:
        key = change_key(
            problem.group_name, problem.field_name, problem.symbol
        )
        rejected[key] = (REJECTED, problem.message)
    if problems:
        return None, rejected

    return rebuilt, rejected


def _build(
    revision: int,
    changes: list[ParameterChange],
    previous: ParameterValues | None,
) -> ParameterValues:
    by_group: dict[str, dict[str, object]] = {}
    by_symbol_fields: dict[str, dict[str, dict[str, object]]] = {}
    for change in changes:
        target = (
            by_group
            if change.symbol == ALL_SYMBOLS
            else by_symbol_fields.setdefault(change.symbol, {})
        )
        target.setdefault(change.group_name, {})[change.field_name] = (
            change.value
        )

    defaults = {
        group: _construct(group, by_group.get(group.__name__, {}))
        for group in parameter_catalog.GROUPS
    }
    # A symbol's map has to hold every group, not just the overridden
    # ones, so a lookup that falls to it does not miss the rest. Its own
    # fields sit on top of those that apply to every symbol, or setting
    # one field for a symbol would return the rest of that group to the
    # declared defaults.
    by_symbol = {
        symbol: {
            group: (
                _construct(
                    group, by_group.get(group.__name__, {}) | overridden
                )
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
