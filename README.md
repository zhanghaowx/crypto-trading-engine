
# Jolteon (Crypto Trading Engine)


[![codecov](https://codecov.io/gh/zhanghaowx/crypto-trading-engine/branch/main/graph/badge.svg?token=crypto-trading-engine_token_here)](https://codecov.io/gh/zhanghaowx/crypto-trading-engine)
[![CI](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml/badge.svg)](https://github.com/zhanghaowx/crypto-trading-engine/actions/workflows/main.yml)

---
![Under Construction](https://mastersenseigenetics.com/wp-content/uploads/2021/04/UnderConstruction.jpeg)
---
## Overview

Jolteon is a sophisticated trading platform designed for crypto trading, implemented in Python. This platform empowers users to efficiently code and deploy trading strategies on various exchanges with minimal manual intervention.

## Supported Exchanges

- [X] Coinbase (Partially)
- [X] Kraken Spot Exchange

## Features

### 1. Backtesting

Jolteon provides a robust backtesting functionality, allowing users to evaluate the performance of their trading strategies against historical data. This feature aids in refining and optimizing strategies before deploying them in live markets.

### 2. Simulator with Live Market Data

The platform includes a simulator that operates with live market data. This feature creates a realistic environment for users to test their strategies without risking actual capital, facilitating thorough strategy development.

### 3. Automated Order Execution

Jolteon is capable of executing orders autonomously. This feature enables users to implement and automate their trading strategies, reducing the need for constant manual oversight.

### 4. Risk Management Component

To enhance risk control, the platform incorporates a comprehensive risk management component. Users can set parameters for position sizing, implement stop-loss orders, and establish other risk mitigation measures.

### 5. Instrument Scanner

A powerful instrument scanner is integrated into Jolteon, enabling users to identify stocks or cryptocurrencies based on specific criteria. This feature streamlines the process of identifying assets that align with the user's trading strategies.

### 6. Heartbeat Monitor Service

Jolteon includes a heartbeat monitor service to ensure the seamless operation of both external APIs and internal components. This monitoring service automatically checks and alerts users in the event of any issues, ensuring the platform's reliability.

## Getting Started

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — manages both the Python interpreter and dependencies. Install it with
  `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or see the
  [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for other platforms.

The codebase requires **Python 3.11** (it uses `enum.StrEnum`, added in 3.11), pinned in `.python-version`.
You don't need to install Python yourself — `uv` downloads and manages the exact version for you.

### Installation

```bash
git clone https://github.com/zhanghaowx/crypto-trading-engine.git
cd crypto-trading-engine
uv sync    # downloads Python 3.11 if needed, creates .venv, installs the package + dev dependencies
```

This reads `pyproject.toml`/`uv.lock` and produces a `.venv/` — no manual `python3`/virtualenv juggling needed.
Prefix commands with `uv run` (e.g. `uv run jolteon ...`) or `source .venv/bin/activate` once, as you prefer.

> [!NOTE]
> `cryptography` (pulled in by `coinbase-advanced-py`) dropped prebuilt wheels for Intel macOS (x86_64) as of
> version 49; `pyproject.toml` pins it below that so `uv sync` doesn't try to compile it from Rust source.

### Running Jolteon

Jolteon is a single-symbol (`BTC-USD`), single-strategy trading engine, run via the `jolteon` console script
(equivalent to `python -m jolteon`) installed by the steps above.

**Live trading / simulation** against an exchange's live public market data feed:

```bash
uv run jolteon --exchange Kraken     # or --exchange Coinbase
```

Live order execution requires exchange API credentials as environment variables:

| Exchange | Environment variables |
|----------|------------------------|
| Kraken   | `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` |
| Coinbase | `COINBASE_API_KEY`, `COINBASE_API_SECRET` |

> [!NOTE]
> Coinbase support is currently limited to backtesting/replay — live order execution for Coinbase always falls
> back to a mock execution service (see [docs/markdowns/markets/coinbase.md](docs/markdowns/markets/coinbase.md)).

Logs and a SQLite recording of the run are written to `/tmp/jolteon.log` and `/tmp/jolteon.sqlite`.

**Backtesting** against a historical time range:

```bash
uv run jolteon --exchange Kraken --replay-start 2024-01-01T00:00:00 --replay-end 2024-01-02T00:00:00
```

**Replaying a previously recorded SQLite database** (e.g. one produced by an earlier live/replay run):

```bash
uv run jolteon --exchange Kraken --replay-db /tmp/jolteon.sqlite
```

Replay output (log, database, and a cProfile trace) is written under your temp directory (e.g.
`/tmp/replay.log`, `/tmp/replay.sqlite`, `/tmp/jolteon.stat`).

### Running with Docker/Podman

```bash
docker build -t jolteon -f Containerfile .
docker run --rm -e KRAKEN_API_KEY -e KRAKEN_API_SECRET jolteon --exchange Kraken
```

### Running Tests

Task running is handled by [poethepoet](https://poethepoet.natn.io/) (`poe`), with tasks defined in
`pyproject.toml`'s `[tool.poe.tasks]`:

```bash
uv run poe lint         # ruff (lint + format check) + mypy
uv run poe fmt          # auto-fix formatting and import order with ruff
uv run poe test         # lint, then unit tests with coverage (tests/)
uv run poe integration  # lint, then integration tests against live exchanges (integration-tests/)
uv run poe clean        # remove build/test artifacts
```

### Building Documentation

```bash
uv run poe docs      # serves the mkdocs site locally with live reload
```

## Contributing

We welcome contributions! If you would like to contribute to the development of Jolteon, please refer to the [Contribution Guidelines](link-to-contributing).

## License

Jolteon is licensed under the [MIT License](LICENSE). See the [License](LICENSE) file for more details.
