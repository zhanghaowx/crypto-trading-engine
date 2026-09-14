# Multi-exchange plan

## Decision

Add Binance.US as the first venue beside Kraken, beginning with public
market data and paper trading. Do not send live Binance.US orders until the
paper fill model uses trade size and visible depth, and a multi-day venue
comparison shows positive net markout.

Run the engines and dashboard as separate containers under Docker Compose.
This preserves the process isolation the application already relies on while
making the whole stack controllable with one command.

## Why Binance.US

Binance.US currently advertises zero maker fees. That removes the largest
known obstacle in the current strategy: `FeeAwareQuoteOffsetService` has to
place a base-tier Kraken quote roughly 40 bps from fair value before adding
the desired edge, while a zero-fee venue adds only the edge.

Binance.US does not share Binance.com's order book. Its BTC order flow is
much smaller than Kraken's and is divided among BTC/USD, BTC/USDT and
BTC/USDC. Lower cost therefore makes Binance.US worth testing, but does not
establish that it will fill more often or that its fills will have better
markout. BTC/USD and BTC/USDT should both be measured rather than choosing a
pair from the fee schedule alone.

The public API provides the inputs needed for a useful experiment:

- real-time trades and best bid/offer;
- incremental L2 depth with sequence numbers and a REST snapshot procedure;
- symbol filters for price tick, quantity step and minimum notional;
- `LIMIT_MAKER` for authenticated post-only orders; and
- an authenticated endpoint for the account's actual commission rate.

References:

- <https://www.binance.us/fees>
- <https://docs.binance.us/>
- <https://support.binance.us/en/articles/9842798-list-of-supported-and-unsupported-states-and-regions>

## Runtime identity and file layout

An engine is currently identified by symbol alone. That makes two engines for
`BTC/USD` collide in their recording, log, dashboard selection and parameter
scope. Make `(exchange, symbol)` the engine identity before adding the second
adapter.

Use an exchange-first directory layout:

```text
<root>/
  kraken/
    parameters.sqlite
    BTC-USD/
      live.sqlite
      live.log
      live.log.sqlite
  binance-us/
    parameters.sqlite
    BTC-USD/
      live.sqlite
      live.log
      live.log.sqlite
    BTC-USDT/
      live.sqlite
      live.log
      live.log.sqlite
```

Keep one parameter store per exchange. This makes `All symbols` mean all
symbols on the selected venue, prevents a Kraken fee setting from being
offered to a Binance.US engine, and avoids a parameter-store schema migration.
Strategy values that should match across venues can initially be pushed to
each venue separately. Cross-venue parameter profiles can be added later if
that repetition proves costly.

Read the existing `<root>/<symbol>/...` layout as legacy Kraken data so old
recordings remain visible. All new sessions write the exchange-first layout.
Do not infer the exchange from a recorded symbol or filename.

### Files

- `jolteon/engine/core/market.py`: add `BINANCE_US`; make its CLI spelling
  explicit and stable.
- `jolteon/paths.py`: accept an exchange in directory, recording, log and
  parameter-store functions; discover `(exchange, symbol)` pairs; retain a
  read-only legacy Kraken scan.
- `jolteon/app/data.py`: replace the symbol-only `EngineDatabase` identity
  with exchange plus symbol and expose a stable key for widgets and URLs.
- `jolteon/cli.py`: pass the exchange into paths and application construction.
- `tests/test_paths.py`, `tests/app/test_data.py`, and
  `tests/app/test_settings.py`: cover two venues trading the same symbol and
  legacy discovery.

## Exchange boundary

Keep strategy, risk, position, analytics and recording code
exchange-neutral. Venue packages translate wire formats into the existing
`BBO`, `Trade`, `BookUpdate`, `InstrumentSpec`, `Order` and `CancelOrder`
objects.

Create an application factory rather than adding another branch containing
imports to `jolteon/cli.py`:

```text
jolteon/app/
  exchanges.py              # Market -> application/feed/execution/fees
  kraken.py
  binance_us.py

jolteon/engine/market_data/
  kraken/
  binance_us/
    public_feed.py
    parameters.py

jolteon/engine/execution/
  mock_execution_service.py # moved out of kraken/
  kraken/
  binance_us/
    execution_service.py
    rest_client.py
    fee_schedule.py
    parameters.py
```

The registry entry should supply:

- the public market-data feed;
- the live execution service;
- the fee parameter group;
- venue-specific symbol encoding and decoding; and
- the historical data source when the venue supports remote replay.

Move `MockExecutionService` out of the Kraken package. Remove its Kraken REST
trade fallback; live paper mode already receives venue trades, and replay
must be deterministic from its recording. Inject the venue fee schedule
instead of importing `KrakenFeeSchedule` inside the mock.

### Symbol representation

Use canonical `BASE/QUOTE` symbols everywhere below the adapters. Binance.US
maps `BTC/USD` to `BTCUSD` only at its REST and WebSocket boundary. Kraken's
own spelling differences stay in its adapter. Persist the canonical symbol
and exchange in session metadata so the dashboard never has to reconstruct
identity from venue-specific text.

## Fill-model prerequisites

The venue comparison is not trustworthy while known issues 2 and 3 inflate
fills.

### First: cap fills by printed quantity

In
`jolteon/engine/execution/mock_execution_service.py`, a trade through a
resting price must fill no more than both the remaining order quantity and
the observed market-trade quantity. Preserve partial fills across subsequent
prints.

This is the first implementation PR because it is small, deterministic and
uses data already present.

### Second: use L2 depth for queue ahead

Subscribe the mock to `order_book_feed` and retain the current `OrderBook`
for each symbol. When an order rests, initialize `ahead_quantity` from the
visible quantity at its exact price. Continue consuming queue ahead from
opposing prints before filling the simulated order.

This remains an estimate: L2 cannot reveal rank within a level or distinguish
cancellations ahead from cancellations behind. Record the initial queue-ahead
estimate and fill-model version with every simulated order so later analysis
states which assumptions produced it.

Binance.US does not document an L3, order-by-order market-data feed. Its
`<symbol>@depth` stream is sequenced L2: each bid or ask contains a price and
the new aggregate quantity at that price, without public order IDs. The raw
trade stream identifies individual executions, and the private user stream
identifies this account's own orders, but neither reveals every resting order
or its queue rank. Do not describe the Binance.US model as L3 unless the venue
later publishes a distinct supported feed with stable order identifiers.

### Third: preserve depth for replay

Add a compact depth recording rather than flattening every book level into
columns. Store sequenced snapshots and deltas, or periodic snapshots plus
deltas, sufficiently often to rebuild the same book deterministically.
Teach `HistoricalFeed` to publish `order_book_feed` when the recording
contains it and retain the current behavior for legacy recordings.

This closes the live-only limitation in known issue 6 and lets the Binance.US
experiment be repeated instead of existing as one real-time sample.

### Latency

Add configurable outbound-order and cancel latency only after the depth-aware
model is deterministic. Apply fake time during replay and wall-clock time in
live paper mode. Record the configured latency with the session.

## Binance.US public feed

Implement `jolteon/engine/market_data/binance_us/public_feed.py` with these
channels:

- `<symbol>@trade` -> `Trade`;
- `<symbol>@bookTicker` -> `BBO`;
- `<symbol>@depth@100ms` plus `GET /api/v3/depth` -> `BookUpdate`; and
- `GET /api/v3/exchangeInfo` -> `InstrumentSpec`.

Follow Binance.US's snapshot-and-buffer sequence exactly. Reject a depth gap,
clear the local book, request another snapshot, and use the existing market
data health issue while resynchronizing. Reconnect before or at the venue's
24-hour WebSocket lifetime and respond to its ping frames.

Map these exchange filters:

- `PRICE_FILTER.tickSize` -> price increment and precision;
- `LOT_SIZE.stepSize` and `minQty` -> quantity precision and minimum;
- `MIN_NOTIONAL.minNotional` -> minimum cost.

Publish the instrument before enabling strategy quotes. This also provides a
clean solution to known issue 7: feeds declaring `Channel.INSTRUMENT` expose a
readiness signal, and the strategy is connected only after that signal has
arrived. Replays and feeds without the channel remain immediately ready.

## Binance.US fees and execution

For paper mode, add
`jolteon/engine/execution/binance_us/fee_schedule.py` with the advertised zero
maker rate and current taker rate as defaults. Keep both declared parameters
because fees can change.

Authenticated execution is a later milestone:

- sign requests in `rest_client.py` using `BINANCE_US_API_KEY` and
  `BINANCE_US_API_SECRET`;
- submit post-only quotes as `LIMIT_MAKER` with the engine's client order ID;
- consume user-data-stream `executionReport` events for partial fills,
  fills, cancellations, expirations and self-trade prevention;
- renew the listen key and reconnect before its expiry;
- query `/api/v3/account/commission` at startup and use the account's
  actual maker rate;
- reconcile open orders after every reconnect before placing new ones; and
- cancel all known live orders during graceful shutdown.

Do not enable Binance.US live mode merely because order submission works.
Gate it on explicit integration tests against the venue and the paper
evaluation described below.

## Dashboard

The dashboard continues to read files and never talks directly to an engine.
Add exchange to its selection and labels without duplicating pages.

### Selection

Use two selectors above the Live page content:

1. Exchange, shown when more than one exchange exists.
2. Symbol, containing symbols recorded for the selected exchange.

Bind both to query parameters, for example
`?exchange=binance-us&symbol=BTC%2FUSDT`, so copied links identify one engine
unambiguously. Keep the chosen exchange and symbol in session state across
page switches.

### Page behavior

- Live: read the selected `(exchange, symbol)` recording and show the venue
  beside the symbol.
- Health: group engines by exchange and label each component with both venue
  and symbol.
- Parameters: edit the selected exchange's parameter store. Show only common
  groups plus groups registered by that exchange.
- Logs: add exchange to filters and exported rows.
- Comparison: add a page only after both venues have recordings. Compare the
  same canonical pair over the same time window.

The comparison page should show:

- touch spread distribution and time at each spread;
- trades and notional per minute;
- visible depth near mid;
- quote time, queue ahead and fills per quoted hour;
- partial-fill and full-fill rates;
- gross and net markout at 100 ms, 1 s, 5 s and 30 s;
- adverse selection by side and inventory bucket;
- time at inventory limits; and
- cancel-to-fill ratio.

Use existing native Streamlit pages, fragments, metrics and dataframes. Put
the calculations in `jolteon/app/venue_comparison.py` and keep
`jolteon/app/app_pages/comparison.py` as the direct page script.

### Files

- `jolteon/app/settings.py`: exchange and engine selection state.
- `jolteon/app/dashboard.py`: register the comparison page.
- `jolteon/app/app_pages/live.py`: exchange and symbol controls.
- `jolteon/app/app_pages/health.py` and `engine_health.py`: venue grouping.
- `jolteon/app/app_pages/logs.py`: venue-aware filters.
- `jolteon/app/app_pages/engine_parameters.py`: exchange-specific catalog and
  store.
- `jolteon/app/venue_comparison.py`: pure comparison calculations.
- `jolteon/app/app_pages/comparison.py`: presentation.

## One-command background stack

Use Docker Compose because the engine already has a container image and each
engine must remain a separate process. Running multiple applications inside
one Python process would cross-connect the global signal bus and global
parameter service.

Add:

- `compose.yaml`: dashboard plus one service per configured engine;
- `Containerfile`: an engine target and a dashboard target with the Streamlit
  dependency installed;
- `.env.example`: root, ports and credential names without secrets; and
- `docs/markdowns/operations/local-stack.md`: start, inspect, stop and recover.

Mount one named volume at `/data` and pass `--root /data` to every service.
The initial paper stack should contain:

- Kraken BTC/USD;
- Binance.US BTC/USD;
- Binance.US BTC/USDT; and
- one dashboard on port 8501.

Commands:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f
docker compose down
```

Paper services require no exchange credentials. Put live services behind a
Compose profile so `up -d` cannot start them accidentally. Credentials enter
through environment variables or Docker secrets and are never stored in the
Compose file. Use restart policies for the dashboard and paper engines, but
do not automatically restart a live engine until order reconciliation is
implemented.

## Hosted storage and monitoring

Hosted SQLite and Sentry solve different problems. A hosted database makes
data reachable away from the machine running the engines. Sentry reports
failures and operational signals. Neither replaces the other, and neither is
required to put the local processes under Compose.

### Keep engine recordings local

Do not replace the engine's local SQLite files with a network database. The
current arrangement has useful properties for a trading process:

- recording never waits for an internet round trip;
- exchange connectivity and telemetry connectivity fail independently;
- every database has exactly one writer;
- WAL lets the local dashboard read while the engine writes; and
- a network outage does not lose the session being recorded.

A service such as Turso can expose SQLite-compatible data remotely, but its
remote-primary mode sends writes over the network. Its embedded-replica
documentation also warns against opening the local file while it synchronizes,
which conflicts with the current recorder and dashboard sharing the file.
Turso's newer local-first sync may eventually fit, but adopting a different
database engine and synchronization model is too much risk for the market-data
hot path before multi-exchange behavior is established.

Use the Compose volume as the source of truth. If remote dashboard access or
off-machine recovery becomes necessary, add one of these separately:

1. Periodic, SQLite-safe snapshots to object storage for backup.
2. An asynchronous exporter that reads committed rows and writes an analytics
   copy to Turso or PostgreSQL.
3. A small read-only dashboard API hosted beside the engine, protected with
   authentication, if live remote viewing is the actual need.

The exporter must have a durable cursor per source database and may lag. It
must never be in the order, fill, heartbeat or recording critical path. A
hosted analytics copy is expendable and rebuildable from local recordings.

Turso's current free plan is large enough for an experiment, but pricing is
not the deciding factor; correctness during disconnection is. Revisit it after
compact book recording makes the expected write volume measurable.

References:

- <https://docs.turso.tech/features/embedded-replicas/introduction>
- <https://turso.tech/pricing>

### Add Sentry for unattended processes

Sentry is useful once Compose runs engines in the background because the local
Health page only helps while somebody is looking at it. Add the Python SDK to
both engine and dashboard processes, enabled only when `SENTRY_DSN` is set.
Without that variable, behavior remains entirely local.

Capture:

- uncaught process exceptions;
- exchange connection and resynchronization failures after retries are
  exhausted;
- order submission, cancellation and reconciliation failures;
- SQLite writer failures; and
- dashboard crashes.

Tag every event with `exchange`, canonical `symbol`, `mode` (`paper`, `live`
or `replay`), component, release commit and container/service name. Grouping
then distinguishes a Binance.US feed problem from a Kraken execution problem
without creating a Sentry project per engine.

Do not send normal market data, orders, fills, balances, API responses or every
heartbeat as Sentry events. They are high-volume trading records rather than
exceptions and may contain account information. Filter request headers,
credentials, signed URLs and local variables before transmission. Leave
`send_default_pii` disabled and begin with tracing disabled; add sampled spans
only for a specific latency question.

Keep the existing SQLite logs and health records. Sentry delivery itself
depends on network access, so local records remain the evidence when both the
exchange and monitoring network are unavailable. A short SDK shutdown timeout
must not delay graceful cancellation.

Sentry's Python SDK integrates with standard logging, while its hosted product
can alert on errors, logs and metrics. The current service includes free log
and metric allowances, but only low-volume actionable events should be sent.

References:

- <https://github.com/getsentry/sentry-python>
- <https://sentry.io/changelog/logs-are-generally-available/>
- <https://sentry.io/changelog/application-metrics-are-now-ga/>

### Operational recommendation

Adopt in this order:

1. Local SQLite on a persistent Compose volume.
2. Sentry error reporting for unattended paper engines.
3. SQLite-safe off-machine backups.
4. A hosted analytics copy only when remote querying is needed.

Do not use Sentry as the venue-comparison database or a hosted SQLite service
as the engine's primary recorder.

## Delivery sequence

### PR 1: trustworthy sweep fills

- Cap through-price fills by observed trade quantity.
- Keep partial quantities resting.

Acceptance: a tiny print cannot fill a larger quote, replay stays
deterministic, and Kraken behavior otherwise remains unchanged.

### PR 2: one-command Kraken stack

- Add the multi-stage container build and Compose services.
- Start the existing Kraken paper engine and dashboard with `up -d`.
- Document `up`, `ps`, `logs` and `down`.
- Keep live trading in a disabled profile.

Acceptance: one command starts the Kraken paper engine and dashboard in the
background; one command stops them cleanly; recordings survive recreation.

### PR 2a: opt-in Sentry reporting

- Initialize Sentry from `SENTRY_DSN` in engine and dashboard entrypoints.
- Add exchange, symbol, mode, component and release tags.
- Capture terminal operational failures without exporting trading payloads.
- Document data filtering and verify that an unset DSN sends nothing.

Acceptance: a forced background-process exception appears with enough tags to
identify its engine, while ordinary ticks, trades and heartbeats produce no
Sentry traffic.

### PR 3: exchange identity and paths

- Add `Market.BINANCE_US` and the exchange registry.
- Move the mock execution service out of the Kraken package and inject its
  fee schedule.
- Introduce `(exchange, symbol)` engine identity.
- Write the exchange-first layout and read legacy Kraken recordings.
- Make dashboard and parameter selection exchange-aware.

Acceptance: Kraken and Binance.US BTC/USD recordings coexist and every page
opens the selected one.

### PR 4: Binance.US public market data

- Add trades, BBO, synchronized L2 depth and instrument filters.
- Add reconnect, heartbeat and gap recovery.
- Hold live quotes until instrument readiness.

Acceptance: a long-running feed maintains a synchronized book, emits
canonical symbols and never quotes before venue limits are known.

### PR 5: depth-aware paper execution and replay

- Initialize queue ahead from L2.
- Record fill assumptions and compact book data.
- Replay recorded book updates.

Acceptance: the same recording produces the same orders and fills twice, and
queue ahead is nonzero whenever visible size rests at the quoted price.

### PR 6: complete the multi-venue background stack

- Add the Binance.US BTC/USD and BTC/USDT paper services.
- Verify restart and storage isolation with duplicate symbols across venues.

Acceptance: one command starts three paper engines and the dashboard in the
background; one command stops them cleanly; recordings survive recreation.

### PR 7: venue comparison

- Add the comparison calculations and dashboard page.
- Run both venues concurrently for several days.
- Record the chosen pair and evidence in this document.

Acceptance: results align identical time windows and report gross and net
markout separately from simulated fill count.

### PR 8: authenticated Binance.US execution

- Add commission discovery, post-only orders, user-stream fills, reconnect
  reconciliation and shutdown cancellation.
- Start with venue minimum size and a strict inventory cap.

Acceptance: integration tests demonstrate place, partial fill, cancel,
reconnect and reconciliation behavior before any unattended live session.

## Go/no-go rule

After at least several complete days including more and less active periods,
prefer the Binance.US pair only if it has:

- positive net markout after its actual account fee;
- enough fills to estimate each configured horizon rather than a handful of
  isolated events;
- stable book synchronization and no unexplained sequence gaps;
- acceptable time at the inventory cap; and
- results that remain positive after conservative queue and latency
  assumptions.

Zero maker fees are the reason to run the experiment. They are not the result
of the experiment.
