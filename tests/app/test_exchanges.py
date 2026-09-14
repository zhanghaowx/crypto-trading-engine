import pytest

from jolteon.app.exchanges import exchange_definition, exchanges
from jolteon.engine.core.market import Market


def test_registry_contains_kraken_and_binance_us():
    assert {item.market for item in exchanges()} >= {
        Market.KRAKEN,
        Market.BINANCE_US,
    }


def test_binance_us_translates_symbols_only_at_its_boundary():
    exchange = exchange_definition(Market.BINANCE_US)

    assert exchange.encode_symbol("BTC/USD") == "BTCUSD"
    assert exchange.decode_symbol("BTCUSDT") == "BTC/USDT"


def test_binance_us_rejects_an_ambiguous_wire_symbol():
    with pytest.raises(ValueError, match="Cannot decode"):
        exchange_definition(Market.BINANCE_US).decode_symbol("BTC")
