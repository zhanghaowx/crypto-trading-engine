from dataclasses import dataclass


@dataclass
class ParameterGroupRevision:
    """The available snapshot and the last read of a parameter group.

    ``current_revision`` is the engine's current parameter snapshot.
    ``last_read_revision`` is the revision last requested by any component,
    or None if the group has never been read. Reads are tracked for the
    whole group across all symbols. They do not prove that every component
    has read the group or acted on its values.
    """

    PRIMARY_KEY = "group_name"

    group_name: str
    current_revision: int
    last_read_revision: int | None
