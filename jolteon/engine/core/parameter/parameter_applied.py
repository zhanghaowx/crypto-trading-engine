from dataclasses import dataclass


@dataclass
class ParameterApplied:
    """
    What the engine did with one pushed parameter.

    The engine never writes the store - the dashboard owns that file -
    so this is how a push gets an answer: whether the value was taken,
    and whether a component has read it yet. `observed_revision` behind
    `revision` means the value is stored but the component that uses it
    has not looked since, which is what "takes effect on restart" looks
    like without anyone having declared it.
    """

    PRIMARY_KEY = "key"

    key: str
    group_name: str
    field_name: str
    symbol: str
    stored_value: str
    revision: int
    observed_revision: int
    status: str
    reason: str = ""


TAKEN = "taken"
REJECTED = "rejected"
UNKNOWN = "unknown"


def applied_key(group_name: str, field_name: str, symbol: str) -> str:
    # SQLiteWriter declares a single-column primary key, so the three
    # parts that identify a value are folded into one.
    return f"{group_name}.{field_name}.{symbol}"
