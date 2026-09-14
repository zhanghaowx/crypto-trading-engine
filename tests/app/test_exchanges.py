from unittest.mock import patch

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
    assert exchange.decode_symbol("btc-usd") == "BTC/USD"


def test_kraken_application_is_loaded_through_the_registry():
    with patch("jolteon.app.kraken.KrakenApplication") as application:
        exchange_definition(Market.KRAKEN).application("BTC/USD", paper=True)

    application.assert_called_once_with("BTC/USD", paper=True)


def test_binance_us_application_and_fee_schedule_are_registered():
    exchange = exchange_definition(Market.BINANCE_US)
    with patch("jolteon.app.binance_us.BinanceUsApplication") as application:
        exchange.application("BTC/USD", use_mock_execution=True)

    application.assert_called_once_with("BTC/USD", use_mock_execution=True)
    assert exchange.fee_schedule.__name__ == "BinanceUsFeeSchedule"


def test_binance_us_rejects_an_ambiguous_wire_symbol():
    with pytest.raises(ValueError, match="Cannot decode"):
        exchange_definition(Market.BINANCE_US).decode_symbol("BTC")
