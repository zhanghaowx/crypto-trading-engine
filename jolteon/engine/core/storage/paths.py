"""Path conventions for recordings, logs, and parameter stores."""

from pathlib import Path

DEFAULT_ROOT = "/tmp/jolteon"
LIVE = "live"
REPLAY = "replay"

_PARAMETERS = "parameters.sqlite"
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


def recording(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    return str(symbol_directory(root, exchange, symbol) / f"{session}.sqlite")


def log_file(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    return str(symbol_directory(root, exchange, symbol) / f"{session}.log")


def log_database(
    root: str,
    exchange: object,
    symbol: str | None = None,
    session: str = LIVE,
) -> str:
    return f"{log_file(root, exchange, symbol, session)}.sqlite"


def parameter_store(root: str, exchange: object = "Kraken") -> str:
    return str(exchange_directory(root, exchange) / _PARAMETERS)
