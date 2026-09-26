# Jolteon Repository Instructions

Most changes here are written by coding agents. This file is the contract
they work to: where code lives, what may depend on what, and what has to
pass before a change is finished.

## Repository structure

```text
jolteon/
├── engine/          The trading engine. Knows nothing about how it is
│   │                started or how it is looked at.
│   ├── core/            Engine infrastructure: signals, recording,
│   │                    parameters, health, time, storage paths,
│   │                    run identity and run configuration
│   ├── execution/       Execution services and venue execution adapters
│   ├── market_data/     Feeds, books, historical sources and replay inputs
│   ├── position/        Position state and PnL tracking
│   ├── post_trade/      Engine-side post-trade recording
│   ├── risk_limit/      Trading risk controls
│   ├── strategy/        Strategies and fair-price models
│   └── runtime/         Engine composition and lifecycle
│       ├── engine_runtime.py    EngineRuntime: wires a session together
│       ├── exchange_registry.py Which venues exist and how to build one
│       └── venues/              KrakenRuntime, BinanceUsRuntime
│
├── analysis/        Post-trade calculations over recorded fills and fair
│   │                prices. No Streamlit, no database handles - it is
│   │                handed frames and returns frames.
│   ├── markouts.py          What a fill earned over fair value
│   ├── pnl.py               Realized PnL and cash flow
│   ├── execution_quality.py Quality by side and by inventory held
│   └── signals.py           Whether an adjustment predicted the move
│
├── dashboard/       The Streamlit dashboard.
│   ├── main.py          Entrypoint: builds the navigation
│   ├── config.py        The arguments the dashboard was started with
│   ├── state.py         One viewer's session: engine, run, refresh
│   ├── data/            Reads of an engine recording (read-only)
│   ├── read_models/     Recorded rows rebuilt into something to show
│   ├── services/        Cross-engine questions, such as health
│   ├── ui/              Generic UI: cards, tables, pagination, colors
│   ├── cards/           One card each, and what goes inside it
│   ├── screens/         Pages, each composing cards. Not `pages`:
│   │                    Streamlit takes a folder of that name for
│   │                    its own legacy multipage layout
│   └── static/          CSS and images the dashboard serves
│
└── cli/             Process entrypoints.
    ├── engine.py        argparse, Ctrl-C, profiling, runtime assembly
    └── progress.py      The replay progress bar
```

## Dependency rules

Allowed:

```text
cli       -> engine/runtime -> engine
dashboard -> analysis
dashboard -> engine domain models, read-only
analysis  -> lightweight engine domain models where necessary
```

Forbidden:

```text
engine    -> dashboard
engine    -> cli
engine    -> analysis
analysis  -> dashboard
analysis  -> cli
cli       -> dashboard
```

`tests/architecture/test_dependencies.py` enforces these by reading the
imports out of every module, so a violation fails the suite rather than
waiting for review.

## File placement rules

Before creating a file:

1. Name its one responsibility in a sentence.
2. Look for a package that already owns that responsibility.
3. Put it with the responsibility, not beside whoever calls it.
4. Prefer extending an existing package over adding a new one.

Do not create catch-all modules - `utils.py`, `helpers.py`, `common.py`,
`misc.py` - or another generic `core` package. A module that has started
owning several independent responsibilities should be split.

## Dashboard rules

- Rendering belongs under `dashboard`.
- A calculation that would make sense without Streamlit belongs under
  `analysis`, not here.
- The dashboard only ever reads an engine recording. It does not create
  tables, indexes or rows in one; the recording owns its own schema.
- Card-specific UI belongs with that card under `dashboard/cards`.
- UI that more than one card would want belongs under `dashboard/ui`.
- Rebuilding recorded rows into something showable belongs under
  `dashboard/read_models`, separate from the card that draws it.

## Analysis rules

Put a calculation here when it could reasonably run without Streamlit:
markouts, realized PnL, execution quality, inventory analysis, signal
evaluation. Functions take and return DataFrames; they do not open
databases and they do not draw anything.

## Runtime rules

Engine composition and lifecycle belong under `engine/runtime`:
`EngineRuntime`, the exchange registry, and each venue's runtime. They do
not belong in the dashboard or in a CLI module.

## Tests

Tests mirror the source tree:

```text
jolteon/analysis/pnl.py              tests/analysis/test_pnl.py
jolteon/dashboard/ui/cards/runtime.py
                     tests/dashboard/ui/cards/test_runtime.py
```

The suite runs under pytest's `importlib` import mode, so two test files
may share a basename when the modules they cover do.

This repository holds 100% line coverage. A change that adds a branch
adds the test that exercises it, in the same commit.

The test suite also runs on Windows CI, so a test that opens a file has
to close it before the directory holding it goes away.

## Code style

- Write minimal comments; have code self-explain through clear naming
  and structure. A comment earns its place by saying something the code
  cannot: a constraint, an invariant, or why one approach was taken over
  an obvious alternative.
- Do not explain one class's behaviour by naming an unrelated class;
  nobody will know to update it.
- Plain words, not trading-floor jargon.

## Architecture changes

Adding a top-level package, or moving what a package owns:

- update this file in the same change
- say what moved and why in the PR description
- add or update the architecture tests

## Validation

Before finishing:

```text
uv run poe architecture
uv run poe test
```
