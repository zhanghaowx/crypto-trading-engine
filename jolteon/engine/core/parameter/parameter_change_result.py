from dataclasses import dataclass


@dataclass
class ParameterChangeResult:
    """The engine's response to a saved parameter change.

    ``status`` is TAKEN, REJECTED, or UNKNOWN. ``reason`` explains why a
    change was rejected or the parameter was not recognized.
    ``stored_value`` is the requested value, not necessarily the value
    the engine is using. This record does not track component reads.
    """

    PRIMARY_KEY = "key"

    key: str
    group_name: str
    field_name: str
    symbol: str
    stored_value: str
    status: str
    reason: str = ""


TAKEN = "taken"
REJECTED = "rejected"
UNKNOWN = "unknown"


def change_key(group_name: str, field_name: str, symbol: str) -> str:
    # SQLiteWriter needs one primary-key column for the parameter identity.
    return f"{group_name}.{field_name}.{symbol}"
