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

Paper limit orders fill only when an opposing market trade reaches their
price. A trade through the quote can fill no more than the quantity printed;
visible depth and exact queue rank are not yet fully modeled. See the
[known fill-model limitations](docs/markdowns/design/known-issues.md).

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
uv run jolteon --exchange Kraken --replay-db /tmp/jolteon/BTC-USD/live.sqlite
```

**Another symbol** — `--symbol` takes any pair the venue lists. One engine trades one
symbol, so trading two means running two engines:

```bash
uv run jolteon --exchange Kraken --paper --symbol ETH/USD
```

### Where a session writes

Everything a session writes goes under a directory named after the symbol it traded,
so a second engine never lands on top of the first:

```
/tmp/jolteon/
  parameters.sqlite       # tuning, shared by every engine
  BTC-USD/
    live.sqlite           # every signal the session recorded
    live.log              # and its log, mirrored into live.log.sqlite
  ETH-USD/
    ...
```

`--root` moves all of it somewhere else. A replay writes `replay.sqlite` beside the
live recording for the same symbol, plus a profiler trace at `/tmp/jolteon.stat`.

### Dashboard

A read-only view of a run — health, market data, risk limits, orders and PnL.
It polls the SQLite file, so you can watch a live run or open an old one
([details](docs/markdowns/ui/dashboard.md)):

```bash
uv run poe dashboard
```

### Docker

Start the Kraken BTC/USD paper engine and dashboard in the background:

```bash
cp .env.example .env
docker compose up --build -d
```

Open <http://localhost:8501>, then use these commands to operate the stack:

```bash
docker compose ps
docker compose logs -f
docker compose down
```

The named `jolteon-data` volume keeps recordings and parameters across image and
container recreation. `docker compose down --volumes` also deletes that data.
Change `JOLTEON_DASHBOARD_PORT` in `.env` if port 8501 is already in use.

Live trading is kept behind an explicit profile and does not restart
automatically. After setting both Kraken credentials in `.env`, start only the
live engine and dashboard with:

```bash
docker compose --profile live up --build -d engine-kraken-btc-usd-live dashboard
```

Selecting the live services as above does not start the paper engine. See the
[local stack runbook](docs/markdowns/operations/local-stack.md) for logs,
updates, and data cleanup.

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
