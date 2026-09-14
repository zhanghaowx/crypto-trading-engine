"""Shared exchange-first paths for engine recordings and the dashboard."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = "/tmp/jolteon"
LIVE = "live"
REPLAY = "replay"

_PARAMETERS = "parameters.sqlite"
_EXCHANGE_DIRECTORIES = {"kraken": "Kraken", "binance-us": "Binance.US"}


@dataclass(frozen=True)
class SessionDirectory:
    exchange: str
    symbol: str
    path: Path
    legacy: bool = False


def exchange_directory_name(exchange: object) -> str:
    value = str(getattr(exchange, "value", exchange))
    return value.lower().replace("_", "-").replace(".", "-")


def exchange_name(directory_name: str) -> str:
    return _EXCHANGE_DIRECTORIES.get(directory_name, directory_name)


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


def session_directories(root: str) -> list[SessionDirectory]:
    """Discover exchange-first sessions plus non-duplicated legacy Kraken."""
    directory = Path(root)
    if not directory.is_dir():
        return []

    found: dict[tuple[str, str], SessionDirectory] = {}
    for venue in directory.iterdir():
        if not venue.is_dir() or venue.name not in _EXCHANGE_DIRECTORIES:
            continue
        exchange = exchange_name(venue.name)
        for symbol_dir in venue.iterdir():
            if symbol_dir.is_dir():
                symbol = as_symbol(symbol_dir.name)
                found[(exchange, symbol)] = SessionDirectory(
                    exchange, symbol, symbol_dir
                )

    for symbol_dir in directory.iterdir():
        if not symbol_dir.is_dir() or symbol_dir.name in _EXCHANGE_DIRECTORIES:
            continue
        symbol = as_symbol(symbol_dir.name)
        found.setdefault(
            ("Kraken", symbol),
            SessionDirectory("Kraken", symbol, symbol_dir, legacy=True),
        )
    return sorted(
        found.values(), key=lambda item: (item.exchange, item.symbol)
    )


def traded_symbols(root: str) -> list[str]:
    """Compatibility helper for callers that only need symbols."""
    return [item.symbol for item in session_directories(root)]


def prepare(*file_paths: str) -> None:
    for path in file_paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
