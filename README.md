# Jolteon (Crypto Trading Engine)

[![codecov](https://codecov.io/gh/zhanghaowx/crypto-trading-engine/branch/main/graph/badge.svg?token=crypto-trading-engine_token_here)](https://codecov.io/gh/zhanghaowx/crypto-trading-engine)
[![CI](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml/badge.svg)](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml)

Jolteon is a small crypto trading engine written in Python. It connects to an
exchange's market data feed, runs a strategy over it, and places orders — either
for real, against a mock execution service (paper trading), or against historical
data (backtesting). Every run is recorded to a SQLite file you can inspect
afterwards in the included dashboard.

> This is a personal project and still rough around the edges. It trades a single
> symbol (`BTC-USD`) with a single strategy.

## What's in it

- **Market data** from Kraken, live over websockets or replayed from history.
- **A market making strategy** that quotes a fixed spread either side of a fair price.
- **Order execution** on Kraken.
- **Risk limits** on inventory size and order frequency.
- **A health monitor** that watches whether feeds and internal components are still alive.
- **A Streamlit dashboard** for reading back a run.

## Install

You need [uv](https://docs.astral.sh/uv/). It fetches the right Python (3.11) for you,
so you don't need to install Python or set up a virtualenv yourself.

```bash
git clone https://github.com/zhanghaowx/crypto-trading-engine.git
cd crypto-trading-engine
uv sync
```

Run things with `uv run ...`, or `source .venv/bin/activate` once if you prefer.

## Run it

**Paper trading** — real market data, fake orders. This is the best place to start,
since it generates orders, fills, and risk-limit hits to look at:

```bash
uv run jolteon --exchange Kraken --paper
```

**Live trading** — same thing, but orders are real. Drop `--paper` and set your keys:

```bash
export KRAKEN_API_KEY=... KRAKEN_API_SECRET=...
uv run jolteon --exchange Kraken
```

**Backtest** over a past time range:

```bash
uv run jolteon --exchange Kraken --replay-start 2024-01-01T00:00:00 --replay-end 2024-01-02T00:00:00
```

**Replay a recording** from an earlier run:

```bash
uv run jolteon --exchange Kraken --replay-db /tmp/jolteon.sqlite
```

Live and paper runs write to `/tmp/jolteon.log` and `/tmp/jolteon.sqlite`; replays
write to `/tmp/replay.log`, `/tmp/replay.sqlite`, and a profiler trace at `/tmp/jolteon.stat`.

### Dashboard

A read-only view of a run — health, market data, risk limits, orders and PnL.
It polls the SQLite file, so you can watch a live run or open an old one
([details](docs/markdowns/ui/dashboard.md)):

```bash
uv run poe dashboard
```

### Docker

```bash
docker build -t jolteon -f Containerfile .
docker run --rm -e KRAKEN_API_KEY -e KRAKEN_API_SECRET jolteon --exchange Kraken
```

## Development

Tasks run through [poe](https://poethepoet.natn.io/):

```bash
uv run poe fmt          # format and sort imports
uv run poe lint         # ruff + mypy
uv run poe test         # lint, then unit tests with coverage
uv run poe integration  # lint, then tests against the live exchange
uv run poe docs         # serve the mkdocs site locally
uv run poe clean        # delete build and test artifacts
```

A `poe` sequence stops at the first failure, so a broken `poe lint` hides the tests
behind it. Fix and re-run to see the rest.

To run the same checks before every push:

```bash
git config core.hooksPath .githooks
```

`git clone` doesn't install hooks, so this is once per clone. `git push --no-verify` skips it.

## Contributing

Fork it, work on a branch, open a pull request.

## License

[MIT](LICENSE).
