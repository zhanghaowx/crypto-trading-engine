"""Registry of venue adapters exposed to the engine CLI."""

from dataclasses import dataclass
from typing import Callable

from jolteon.app.trading_application import TradingApplication
from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.market import Market
from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)
from jolteon.engine.execution.kraken.fee_schedule import KrakenFeeSchedule


def _canonical(symbol: str) -> str:
    return symbol.replace("-", "/").upper()


def _binance_wire(symbol: str) -> str:
    return _canonical(symbol).replace("/", "")


def _binance_canonical(symbol: str) -> str:
    wire = symbol.upper()
    if "/" in wire or "-" in wire:
        return _canonical(wire)
    for quote in ("USDT", "USDC", "USD"):
        if wire.endswith(quote) and len(wire) > len(quote):
            return f"{wire[: -len(quote)]}/{quote}"
    raise ValueError(f"Cannot decode Binance.US symbol {symbol}")


def _kraken_application(*args, **kwargs) -> TradingApplication:
    from jolteon.app.kraken import KrakenApplication

    return KrakenApplication(*args, **kwargs)


def _binance_us_application(*args, **kwargs) -> TradingApplication:
    from jolteon.app.binance_us import BinanceUsApplication

    return BinanceUsApplication(*args, **kwargs)


@dataclass(frozen=True)
class ExchangeDefinition:
    market: Market
    name: str
    path_name: str
    application: Callable[..., TradingApplication] | None
    fee_schedule: type[FeeSchedule] | None
    encode_symbol: Callable[[str], str]
    decode_symbol: Callable[[str], str]
    supports_remote_history: bool


_EXCHANGES = {
    Market.MOCK: ExchangeDefinition(
        market=Market.MOCK,
        name="Mock",
        path_name="mock",
        application=None,
        fee_schedule=None,
        encode_symbol=_canonical,
        decode_symbol=_canonical,
        supports_remote_history=False,
    ),
    Market.KRAKEN: ExchangeDefinition(
        market=Market.KRAKEN,
        name="Kraken",
        path_name="kraken",
        application=_kraken_application,
        fee_schedule=KrakenFeeSchedule,
        encode_symbol=_canonical,
        decode_symbol=_canonical,
        supports_remote_history=True,
    ),
    Market.BINANCE_US: ExchangeDefinition(
        market=Market.BINANCE_US,
        name="Binance.US",
        path_name="binance-us",
        application=_binance_us_application,
        fee_schedule=BinanceUsFeeSchedule,
        encode_symbol=_binance_wire,
        decode_symbol=_binance_canonical,
        supports_remote_history=False,
    ),
}


def exchange_definition(market: Market) -> ExchangeDefinition:
    return _EXCHANGES[market]


def exchanges() -> tuple[ExchangeDefinition, ...]:
    return tuple(_EXCHANGES.values())
