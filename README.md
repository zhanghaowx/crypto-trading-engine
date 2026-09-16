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
the simulator makes its best queue-position guess from visible L2 quantity at
the exact order price. L2 cannot reveal exact queue rank or whether later
cancellations were ahead of the simulated order. See the
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
uv run jolteon --exchange Kraken --replay-db /tmp/jolteon/kraken/BTC-USD/live.sqlite
```

New recordings contain compact, versioned L2 snapshots and deltas. Local
replay rebuilds the same exchange-neutral `OrderBook` used during live paper
trading. Older trade-only recordings remain replayable and use the legacy
queue behavior. The recording identifies its book model explicitly
so a future L3 feed can retain order-level data instead of being reduced to L2.

**Another symbol** — `--symbol` takes any pair the venue lists. One engine trades one
symbol, so trading two means running two engines:

```bash
uv run jolteon --exchange Kraken --paper --symbol ETH/USD
```

**Binance.US paper trading** uses the public trade, best-bid/offer and
synchronized L2 depth streams. It loads the venue's price, quantity and
minimum-notional filters before the strategy can place its first quote:

```bash
uv run jolteon --exchange Binance.US --paper --symbol BTC/USD
```

Binance.US live order submission and remote historical replay are intentionally
disabled until their later rollout steps. The public WebSocket requires no API
credentials.

Every service has one in-memory health state. The engine's `HealthMonitor`
derives its health from parameters, market data, and execution; the strategy
quotes only after initialization completes. A warning is visible in the
dashboard while trading continues. A critical issue withdraws existing quotes
and makes both paper and live execution reject new orders until the service
recovers. Historical replay becomes healthy after its data has loaded, so it
does not depend on live-only instrument messages.

The application creates one `HealthMonitor` and passes it to each service.
Receiving that monitor makes the service part of the trading-health decision;
there is no separate registry or `required_for_trading` flag.

### Where a session writes

Everything a session writes is scoped first by exchange and then by canonical
symbol. Two venues trading BTC/USD therefore never share a database or parameter
store:

```
/tmp/jolteon/
  kraken/
    parameters.sqlite     # tuning shared by Kraken engines
    BTC-USD/
      live.sqlite         # every signal the session recorded
      live.log            # and its log, mirrored into live.log.sqlite
  binance-us/
    parameters.sqlite     # separate venue-specific tuning
    BTC-USD/
      live.sqlite
      live.log
```

`--root` moves all of it somewhere else. A replay writes `replay.sqlite` beside the
live recording for the same exchange and symbol, plus a profiler trace at
`/tmp/jolteon.stat`. The dashboard still reads recordings written under the old
`<root>/<symbol>/` layout as legacy Kraken sessions; new runs always use the
exchange-first layout.

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

### Error reporting

Jolteon keeps operational data in local SQLite files. For unattended runs, you
can additionally set `SENTRY_DSN` in `.env` or the process environment to send
terminal exceptions to Sentry. Leaving it unset sends nothing.

Reports identify the exchange, canonical symbol, run mode, process component,
release, and Compose service. Request data, user data, credentials, signed
values, and stack-frame local variables are removed before an event is sent.
Normal ticks, trades, orders, fills, and heartbeats are never sent. Set
`JOLTEON_RELEASE` to the deployed commit SHA and `JOLTEON_ENVIRONMENT` to a name
such as `paper-us` when running outside local development.

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
