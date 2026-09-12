from jolteon.engine.core.parameter.parameter_service import (
    ParameterValues,
    assert_within_bounds,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
)

# Every group the engine reads and the dashboard offers for editing.
# A group listed here needs nothing else to appear on the Parameters
# page: it is rendered from what its fields declare.
GROUPS: tuple[type[ParameterGroup], ...] = ()


def group_by_name() -> dict[str, type[ParameterGroup]]:
    return {group.__name__: group for group in GROUPS}


def validate(values: ParameterValues) -> list[str]:
    """
    Returns: A message for every constraint the given values break.

    Field bounds are checked here too so one pass reports everything
    wrong with a pushed revision, rather than stopping at the first.
    """
    problems = []
    for group in GROUPS:
        current = values.get(group)
        for definition in definitions(group):
            try:
                assert_within_bounds(
                    group, definition, getattr(current, definition.name)
                )
            except AssertionError as error:
                problems.append(str(error))
    return problems
