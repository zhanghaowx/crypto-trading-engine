# Coinbase

> [!WARNING]
> Live order execution for Coinbase is on hold: it always falls back to a mock execution service.
> Only market data and replay/backtesting are functional today.

[Coinbase](https://www.coinbase.com/home) is one of the largest cryptocurrency exchanges in the
United States by trading volume. Jolteon integrates with it over Coinbase's REST and WebSocket
[Advanced Trade API](https://docs.cdp.coinbase.com/advanced-trade/docs/welcome), via the
[coinbase-advanced-py](https://github.com/coinbase/coinbase-advanced-py) SDK.

## Order Entry
* REST API (`coinbase.rest.RESTClient`), used only by the mock execution service — no live order
  entry is implemented for Coinbase yet.

## Market Data
* WebSocket feed for real-time market data.
* REST API for historical candles, used by the replay/backtesting data source.
