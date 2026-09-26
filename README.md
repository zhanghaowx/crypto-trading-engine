# Jolteon (Crypto Trading Engine)

[![codecov](https://codecov.io/gh/zhanghaowx/crypto-trading-engine/branch/main/graph/badge.svg?token=crypto-trading-engine_token_here)](https://codecov.io/gh/zhanghaowx/crypto-trading-engine)
[![CI](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml/badge.svg)](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml)

Jolteon is a small crypto trading engine written in Python. It connects to an
exchange's market data feed, runs a strategy over it, and places orders — either
for real, against a mock execution service (paper trading), or against historical
data (backtesting). Every run is recorded to a SQLite file you can inspect
afterwards in the included dashboard.

> This is a personal project and still rough around the edges. Each engine
> process trades one symbol with one strategy.

Whether the strategy is actually profitable remains an open question.

## What's in it

- **Market data** from Kraken and Binance.US over live websockets; Kraken also supports remote historical replay. Both venues support replay of locally recorded data.
- **A market making strategy** that quotes a fixed spread either side of a fair price.
- **Order execution** live on Kraken and simulated for paper trading on both exchanges.
- **Risk limits** on inventory size and order frequency.
- **A health monitor** that watches whether feeds and internal components are still alive.
- **A Streamlit dashboard** for reading back a run.

## Install

You need [uv](https://docs.astral.sh/uv/). It fetches the right Python (3.11) for you,
so you don't need to install Python or set up a virtualenv yourself.

```
git clone https://github.com/zhanghaowx/crypto-trading-engine.git
cd crypto-trading-engine
uv sync
```

Run things with `uv run ...`, or `source .venv/bin/activate` once if you prefer.

## Run it

**Paper trading** — real market data, fake orders. The best place to start:

```
uv run jolteon --exchange Kraken --paper
```

Paper fills use an estimated L2 queue position. Exact queue priority is unknown, so simulated profitability may differ from live results.

**Live trading** — orders are real. Start with paper trading first. Kraken API credentials must permit querying closed orders and trades to retrieve execution details:

```bash
export KRAKEN_API_KEY=... KRAKEN_API_SECRET=...
uv run jolteon --exchange Kraken
```

Stable fill IDs prevent duplicate recording within a running execution service, but do not provide restart recovery or persistent exactly-once delivery.

**Backtest** over a past time range:

```
uv run jolteon --exchange Kraken --replay-start 2024-01-01T00:00:00 --replay-end 2024-01-02T00:00:00
```

**Replay a recording** from an earlier run:

```
uv run jolteon --exchange Kraken --replay-db /tmp/jolteon/kraken/BTC-USD/live.sqlite
```

**Binance.US paper trading:**

```
uv run jolteon --exchange Binance.US --paper --symbol BTC/USD
```

Binance.US live order submission and remote historical replay are not available.

For deterministic local experiments with explicit inputs and playback speed,
see [Recorded-market replay](docs/replay.md).

**Another symbol** — `--symbol` takes any pair the venue lists. One engine trades one
symbol, so trading two means running two engines:

```
uv run jolteon --exchange Kraken --paper --symbol ETH/USD
```

Sessions write under `/tmp/jolteon` (`--root` moves it). Read them back with the dashboard:

```
uv run poe dashboard
```

### Docker quick start

Start the Kraken paper engine and dashboard using [Compose](compose.yaml):

```bash
cp .env.example .env
docker compose up --build -d
```

Open <http://localhost:8501>. The `jolteon-data` volume persists recordings; `docker compose down --volumes` deletes that data. Live trading requires the explicit `live` profile and configured credentials.

## Development

Planned work and known limitations are tracked in [GitHub Issues](https://github.com/zhanghaowx/crypto-trading-engine/issues).

Checks run through [poe](https://poethepoet.natn.io/); `uv run poe test` runs lint and unit tests. See `pyproject.toml` for the full task list.

To run the same checks before every push:

```
git config core.hooksPath .githooks
```

(`git clone` doesn't install hooks, so this is once per clone.)

## Contributing

Fork it, work on a branch, open a pull request.

## License

[MIT](LICENSE)
