from jolteon.engine.core.storage import paths
from jolteon.engine.core.storage.exchange_instrument_directory_discovery import (  # noqa: E501
    ExchangeInstrumentDirectory,
    discover_exchange_instrument_directories,
    traded_symbols,
)


def test_discovers_the_same_symbol_on_two_exchanges(tmp_path):
    paths.symbol_directory(str(tmp_path), "Kraken", "BTC/USD").mkdir(
        parents=True
    )
    paths.symbol_directory(str(tmp_path), "Binance.US", "BTC/USD").mkdir(
        parents=True
    )

    found = discover_exchange_instrument_directories(str(tmp_path))

    assert [(item.exchange, item.symbol) for item in found] == [
        ("Binance.US", "BTC/USD"),
        ("Kraken", "BTC/USD"),
    ]
    assert traded_symbols(str(tmp_path)) == [
        "BTC/USD",
        "BTC/USD",
    ]


def test_reads_legacy_kraken_layout(tmp_path):
    legacy = paths.symbol_directory(str(tmp_path), "ETH/USD")
    legacy.mkdir(parents=True)

    assert discover_exchange_instrument_directories(str(tmp_path)) == [
        ExchangeInstrumentDirectory("Kraken", "ETH/USD", legacy, legacy=True)
    ]


def test_exchange_directory_wins_over_duplicate_legacy_directory(tmp_path):
    paths.symbol_directory(str(tmp_path), "BTC/USD").mkdir(parents=True)
    current = paths.symbol_directory(str(tmp_path), "Kraken", "BTC/USD")
    current.mkdir(parents=True)

    assert discover_exchange_instrument_directories(str(tmp_path)) == [
        ExchangeInstrumentDirectory("Kraken", "BTC/USD", current)
    ]
