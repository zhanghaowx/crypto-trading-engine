from unittest.mock import patch

import pytest

from jolteon.engine.core.market import Market
from jolteon.engine.runtime.exchange_registry import (
    exchange_definition,
    exchanges,
)


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


def test_kraken_runtime_is_loaded_through_the_registry():
    with patch(
        "jolteon.engine.runtime.venues.kraken.KrakenRuntime"
    ) as runtime:
        exchange_definition(Market.KRAKEN).runtime("BTC/USD", paper=True)

    runtime.assert_called_once_with("BTC/USD", paper=True)


def test_binance_us_runtime_and_fee_schedule_are_registered():
    exchange = exchange_definition(Market.BINANCE_US)
    with patch(
        "jolteon.engine.runtime.venues.binance_us.BinanceUsRuntime"
    ) as runtime:
        exchange.runtime("BTC/USD", use_mock_execution=True)

    runtime.assert_called_once_with("BTC/USD", use_mock_execution=True)
    assert exchange.fee_schedule.__name__ == "BinanceUsFeeSchedule"


def test_binance_us_rejects_an_ambiguous_wire_symbol():
    with pytest.raises(ValueError, match="Cannot decode"):
        exchange_definition(Market.BINANCE_US).decode_symbol("BTC")
