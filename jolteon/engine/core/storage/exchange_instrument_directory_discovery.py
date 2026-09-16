"""Discover exchange instrument directories, including legacy Kraken."""

from dataclasses import dataclass
from pathlib import Path

from jolteon.engine.core.storage import paths


@dataclass(frozen=True)
class ExchangeInstrumentDirectory:
    """Storage directory for an exchange and symbol, shared across runs."""

    exchange: str
    symbol: str
    path: Path
    legacy: bool = False


def discover_exchange_instrument_directories(
    root: str,
) -> list[ExchangeInstrumentDirectory]:
    """Find exchange instrument directories, preferring the current layout."""
    directory = Path(root)
    if not directory.is_dir():
        return []

    found: dict[tuple[str, str], ExchangeInstrumentDirectory] = {}
    for venue in directory.iterdir():
        if not venue.is_dir() or venue.name not in paths.EXCHANGE_DIRECTORIES:
            continue
        exchange = paths.exchange_name(venue.name)
        for symbol_dir in venue.iterdir():
            if symbol_dir.is_dir():
                symbol = paths.as_symbol(symbol_dir.name)
                found[(exchange, symbol)] = ExchangeInstrumentDirectory(
                    exchange, symbol, symbol_dir
                )

    for symbol_dir in directory.iterdir():
        if (
            not symbol_dir.is_dir()
            or symbol_dir.name in paths.EXCHANGE_DIRECTORIES
        ):
            continue
        symbol = paths.as_symbol(symbol_dir.name)
        found.setdefault(
            ("Kraken", symbol),
            ExchangeInstrumentDirectory(
                "Kraken", symbol, symbol_dir, legacy=True
            ),
        )
    return sorted(
        found.values(), key=lambda item: (item.exchange, item.symbol)
    )


def traded_symbols(root: str) -> list[str]:
    """Compatibility helper for callers that only need symbols."""
    return [
        item.symbol for item in discover_exchange_instrument_directories(root)
    ]
