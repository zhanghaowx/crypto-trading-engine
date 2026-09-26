"""Path conventions for recordings, logs, and parameter stores.

An engine writes one recording per run, named by the run's id, with the
run's log and log database beside it:

    <root>/<exchange>/<symbol>/<run_id>.sqlite
    <root>/<exchange>/<symbol>/<run_id>.log
    <root>/<exchange>/<symbol>/<run_id>.log.sqlite

Whether a run read a live feed or a recording is written into the
recording itself, not into the file name.
"""

from pathlib import Path

DEFAULT_ROOT = "/tmp/jolteon"
# The session names of the layout before one file per run, when every
# run of an instrument went into `live.sqlite` or `replay.sqlite`. Kept so
# recordings made under it can still be read.
LIVE = "live"
REPLAY = "replay"

PARAMETERS = "parameters.sqlite"
EXCHANGE_DIRECTORIES = {"kraken": "Kraken", "binance-us": "Binance.US"}


def exchange_directory_name(exchange: object) -> str:
    value = str(getattr(exchange, "value", exchange))
    return value.lower().replace("_", "-").replace(".", "-")


def exchange_name(directory_name: str) -> str:
    return EXCHANGE_DIRECTORIES.get(directory_name, directory_name)


def as_directory_name(symbol: str) -> str:
    return symbol.replace("/", "-")


def as_symbol(directory_name: str) -> str:
    base, separator, quote = directory_name.rpartition("-")
    return f"{base}/{quote}" if separator else directory_name


def exchange_directory(root: str, exchange: object) -> Path:
    return Path(root) / exchange_directory_name(exchange)


def symbol_directory(
    root: str, exchange: object, symbol: str | None = None
) -> Path:
    """Return an exchange-first path; two arguments retain legacy access."""
    if symbol is None:
        return Path(root) / as_directory_name(str(exchange))
    return exchange_directory(root, exchange) / as_directory_name(symbol)


def run_recording(
    root: str, exchange: object, symbol: str, run_id: str
) -> str:
    return str(symbol_directory(root, exchange, symbol) / f"{run_id}.sqlite")


def run_log_file(root: str, exchange: object, symbol: str, run_id: str) -> str:
    return str(symbol_directory(root, exchange, symbol) / f"{run_id}.log")


def run_log_database(
    root: str, exchange: object, symbol: str, run_id: str
) -> str:
    return f"{run_log_file(root, exchange, symbol, run_id)}.sqlite"


def recording(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    """Where the layout before one file per run kept a session's
    recording. For reading recordings made under it; a new run writes to
    `run_recording`."""
    return str(symbol_directory(root, exchange, symbol) / f"{session}.sqlite")


def log_file(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    """Where the layout before one file per run kept a session's log. For
    reading logs made under it; a new run writes to `run_log_file`."""
    return str(symbol_directory(root, exchange, symbol) / f"{session}.log")


def log_database(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    """Where the layout before one file per run kept a session's log
    database. For reading logs made under it; a new run writes to
    `run_log_database`."""
    return f"{log_file(root, exchange, symbol, session)}.sqlite"


def parameter_store(root: str, exchange: object = "Kraken") -> str:
    return str(exchange_directory(root, exchange) / PARAMETERS)
