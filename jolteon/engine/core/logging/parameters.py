from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class LoggingParameters(ParameterGroup):
    max_logfile_bytes: int = parameter(
        10 * 1024 * 1024,
        minimum=1024,
        maximum=1024 * 1024 * 1024,
        step=1024 * 1024,
        unit="bytes",
        description="How large a log file grows before it is rotated.",
    )
    logfile_backup_count: int = parameter(
        5,
        minimum=0,
        maximum=100,
        step=1,
        unit="files",
        description="How many rotated log files are kept.",
    )
    max_log_rows: int = parameter(
        200_000,
        minimum=1,
        maximum=10_000_000,
        step=10_000,
        unit="rows",
        description=(
            "How many log lines the log database keeps. The dashboard "
            "reads this table, so it is trimmed rather than grown."
        ),
    )
    prune_interval: int = parameter(
        1_000,
        minimum=1,
        maximum=1_000_000,
        step=100,
        unit="rows",
        description="How many log lines are written between trims.",
    )
