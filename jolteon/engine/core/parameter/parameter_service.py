from abc import ABC, abstractmethod
from typing import TypeVar

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterDefinition,
    ParameterGroup,
    definitions,
)

P = TypeVar("P", bound=ParameterGroup)

ALL_SYMBOLS = ""


class ParameterValues:
    """
    Every group's values as of one revision, already built.

    Reading is two dictionary lookups against instances constructed off
    the engine's threads, so a strategy can read a parameter on every
    tick without allocating or touching a file.
    """

    __slots__ = ("revision", "_by_symbol", "_defaults", "observed")

    def __init__(
        self,
        revision: int,
        defaults: dict[type, ParameterGroup],
        by_symbol: dict[str, dict[type, ParameterGroup]],
        observed: dict[type, int] | None = None,
    ):
        self.revision = revision
        self._defaults = defaults
        self._by_symbol = by_symbol
        # Carried forward across revisions, so it records the last
        # revision at which each group was genuinely read rather than the
        # last one in which it existed.
        self.observed = dict(observed or {})

    def get(self, group: type[P], symbol: str = ALL_SYMBOLS) -> P:
        """
        Returns: One group's values, recording that a component has now
        read this revision of it.
        """
        self.observed[group] = self.revision
        return self.peek(group, symbol)

    def peek(self, group: type[P], symbol: str = ALL_SYMBOLS) -> P:
        """
        Returns: The same values as get(), without counting as a read.

        Validating or reporting on a revision must not make it look as
        though the component that uses it has picked it up.
        """
        values = self._by_symbol.get(symbol, self._defaults)
        found = values.get(group)
        if found is None:
            found = self._defaults.setdefault(group, group())  # type: ignore[call-arg]
        return found  # type: ignore[return-value]


class IParameterService(ABC):
    """
    The one place the engine reads a tunable from.

    Implementations decide where values come from; components only ask
    for the group they own, so a component never learns whether its
    numbers are hardcoded defaults or were pushed from a dashboard while
    it was running.
    """

    @abstractmethod
    def values(self) -> ParameterValues:
        """
        Returns: Every group's values at a single revision.

        Needed only by a caller that reads two groups and requires them
        to agree with each other, since separate get() calls can fall
        either side of a background refresh. Everyone else wants get().
        """
        raise NotImplementedError  # pragma: no cover

    def get(self, group: type[P], symbol: str = ALL_SYMBOLS) -> P:
        """
        Returns: The current values for one group.
        """
        return self.values().get(group, symbol)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class StaticParameterService(IParameterService):
    """
    Fixed values that never change while running: each group's declared
    defaults, unless an explicit group instance was passed in. The
    starting point for a session nothing is tuning, and the service a
    test reaches for when it wants one specific number changed.
    """

    def __init__(self, *groups: ParameterGroup):
        for group in groups:
            for definition in definitions(type(group)):
                assert_within_bounds(
                    type(group), definition, getattr(group, definition.name)
                )
        self._values = ParameterValues(
            revision=0,
            defaults={type(group): group for group in groups},
            by_symbol={},
        )

    def values(self) -> ParameterValues:
        return self._values


def assert_within_bounds(
    group: type[ParameterGroup],
    definition: ParameterDefinition,
    value: float,
) -> None:
    name = f"{group.__name__}.{definition.name}"
    if definition.minimum is not None:
        assert value >= definition.minimum, (
            f"{name} must be at least {definition.minimum}, got {value}"
        )
    if definition.maximum is not None:
        assert value <= definition.maximum, (
            f"{name} must be at most {definition.maximum}, got {value}"
        )
