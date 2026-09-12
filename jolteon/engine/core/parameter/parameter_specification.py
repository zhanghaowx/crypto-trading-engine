from dataclasses import dataclass, field, fields, replace
from typing import Any


class ParameterGroup:
    """
    Marker base for a dataclass holding one component's tunable values.

    A group declares every value the component would otherwise hardcode,
    using `parameter()` so each field carries its own bounds, unit and
    description. That is what lets the dashboard render an editor for a
    group it has never heard of, and what makes adding a tunable a
    one-line change instead of a change in two processes.

    A group deliberately says nothing about when a change to it takes
    effect. Where a component reads a value is a property of that
    component's code and changes with it, so a declaration here would
    quietly go stale; see ParameterValues.observed for how that question
    is answered from what actually happened at runtime instead.
    """


@dataclass(frozen=True)
class ParameterDefinition:
    """
    Everything known about a single tunable: what it is called, what it
    holds, and how to present and bound it.

    `parameter()` records one of these without a name or type, since
    neither is known at the point of declaration; `definitions()` fills
    them in from the dataclass field.
    """

    name: str = ""
    value_type: type = float
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    number_format: str | None = None
    unit: str = ""
    choices: tuple[Any, ...] | None = None
    description: str = ""


_DEFINITION_KEY = "jolteon.parameter"


def parameter(
    default: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    number_format: str | None = None,
    unit: str = "",
    choices: tuple[Any, ...] | None = None,
    description: str = "",
) -> Any:
    """
    Declares one tunable field of a ParameterGroup.

    Returns Any rather than the field's real type because mypy only
    recognises a literal dataclasses.field() call as supplying a default;
    through a wrapper it would read every `x: float = parameter(...)` as
    assigning the wrong type. The cost is that mypy can no longer catch a
    field declared without a default either, so test_parameter_catalog
    asserts every field has one.
    """
    return field(
        default=default,
        metadata={
            _DEFINITION_KEY: ParameterDefinition(
                default=default,
                minimum=minimum,
                maximum=maximum,
                step=step,
                number_format=number_format,
                unit=unit,
                choices=choices,
                description=description,
            )
        },
    )


def definitions(
    group: type[ParameterGroup],
) -> tuple[ParameterDefinition, ...]:
    """
    Returns: A definition for every field of `group`, in declared order.

    A field assigned a plain default rather than `parameter()` carries no
    metadata, and yields a bare definition instead of raising, so one
    such field cannot break a page rendering a whole catalog.
    """
    return tuple(
        replace(
            f.metadata.get(_DEFINITION_KEY, ParameterDefinition()),
            name=f.name,
            value_type=f.type,
            default=f.default,
        )
        for f in fields(group)  # type: ignore[arg-type]
    )
