# Dashboard

Jolteon ships a [Streamlit](https://streamlit.io/) dashboard for watching a run's health, market
data, risk limits, and orders/PnL. It is a read-only viewer: it never talks to the running engine
directly, and instead polls the SQLite database that `SignalRecorder` already writes every recorded
signal into (in WAL mode, so the reads never block the engine's own writes). This means it runs as a
completely separate process from the engine and can be pointed at either a live run's database or a
replay's.

## Running it

```bash
uv run poe dashboard                                   # reads /tmp/jolteon.sqlite by default
streamlit run jolteon/app/dashboard.py -- --db /tmp/replay.sqlite   # point at a specific database
```

## Sections

* **Health** — heartbeat status for each monitored component, shown first since a stale component
  makes everything below it stale too.
* **Market Data** — recent candlesticks and BBO for the traded symbol.
* **Risk Limits** — current state of the configured risk limits (order frequency, inventory, ...).
* **Orders & PnL** — recorded orders, fills, and running PnL.

A settings popover in the top right controls strategy parameters and the auto-refresh interval.
