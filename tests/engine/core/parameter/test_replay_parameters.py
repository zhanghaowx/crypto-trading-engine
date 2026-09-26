import pytest

from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_specification import definitions
from jolteon.engine.core.parameter.replay_parameters import (
    recorded_value,
    resolved_parameters,
)


def _boolean_fields() -> list[tuple[str, str]]:
    return [
        (group.__name__, definition.name)
        for group in GROUPS
        for definition in definitions(group)
        if definition.value_type is bool
    ]


def test_every_boolean_the_catalog_declares_reads_back_as_a_boolean():
    """
    Driven by the catalog rather than by name, so a boolean added to
    any group is covered the moment it is declared.
    """
    booleans = _boolean_fields()
    assert booleans
    for group, field in booleans:
        assert recorded_value(group, field, 1) is True
        assert recorded_value(group, field, 0) is False


@pytest.mark.parametrize(
    "group,field,value",
    [
        ("SqliteWriterParameters", "max_batch", 1),
        ("HeartbeatParameters", "interval_in_seconds", 1.0),
        ("KrakenFeeSchedule", "stablecoin_pair", True),
        ("KrakenFeeSchedule", "no_such_field", 1),
        ("NoSuchParameters", "stablecoin_pair", 1),
    ],
)
def test_anything_else_is_returned_as_recorded(group, field, value):
    returned = recorded_value(group, field, value)
    assert returned == value
    assert type(returned) is type(value)


def test_an_integer_outside_zero_and_one_is_not_laundered_into_a_boolean(
    replay_dataset,
):
    _, document = replay_dataset
    scopes = document["configuration"]["parameters"]
    scopes[""]["KrakenFeeSchedule"]["stablecoin_pair"] = recorded_value(
        "KrakenFeeSchedule", "stablecoin_pair", 2
    )
    with pytest.raises(ValueError, match="Invalid parameter type"):
        resolved_parameters(scopes)
