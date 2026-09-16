# crypto-trading-engine — Unified Known Issues & Refactoring Roadmap

**Repository:** `zhanghaowx/crypto-trading-engine`
**Branch reviewed:** `main`
**Updated:** 2026-09-15 (depth-aware paper execution and replay)
**Combines:** `docs/markdowns/design/known-issues.md` + architecture/refactoring review

---

## Purpose

This document is the single prioritized backlog for the trading engine.

It combines two previously separate perspectives:

1. **Trading/research validity** — whether the market-making strategy can plausibly make money and whether paper/replay fills are realistic enough to support that conclusion.
2. **Engine architecture and live-trading correctness** — whether events, orders, fills, state, persistence, exchange adapters, and runtime lifecycle are safe and maintainable as the engine grows.

The two perspectives are related. A structurally elegant engine with an unrealistic fill model can produce misleading research, while a profitable model built on fragile event ordering or incorrect order state is unsafe to trade live.

The repository does **not** need a broad rewrite. Its package structure is already sensible. The priority is to repair a small number of correctness and ownership boundaries, then improve simulation fidelity and scalability incrementally.

---

# Priority definition

| Priority | Meaning |
|---|---|
| **P0** | Blocks trustworthy profitability conclusions or safe live trading. Fix before relying on the result or increasing real-money exposure. |
| **P1** | Important for realistic simulation, deterministic behavior, operational safety, or adding exchanges/strategies without compounding technical debt. |
| **P2** | Scaling and maintainability improvements that should follow the core correctness work. |
| **P3** | Cleanup and quality-of-life improvements. Useful, but not on the critical path. |

### Status convention

- **Open** — still requires implementation.
- **Addressed (pending merge)** — implementation exists in an open PR; remove it from the active backlog once merged.
- **Resolved** — implementation is on the main development line.

Within each priority, open issues are ordered approximately by expected impact.

---

# Executive priority list

| # | Priority | Status | Issue | Primary impact |
|---:|:---:|---|---|---|
| 1 | **P0** | Open | Kraken fee economics overwhelm the current quoted edge | Strategy viability |
| 2 | **P0** | Open | Fill identity is not unique in the live Kraken path | PnL / post-trade correctness |
| 3 | **P0** | Open | Event correctness depends on implicit subscriber ordering and a global signal namespace | Accounting / state correctness |
| 4 | ~~P0~~ | **Resolved — PR #60 merged** | Service health is not coordinated at the execution boundary | Live-order safety |
| 5 | **P0** | Open | Strategy owns desired quotes and assumed live-order state in one object | Order lifecycle correctness |
| 6 | ~~P0~~ | **Addressed — PR #61 pending merge** | Simulated queue position is effectively zero for the quotes the strategy actually places | Research validity |
| 7 | ~~P1~~ | **Addressed — PR #61 pending merge** | Replay cannot support the better fill model because full book state is not recorded | Research workflow |
| 8 | **P1** | Open | Sweep fills are not sized from consumed depth | Fill-model realism |
| 9 | **P1** | Open | Paper/replay execution has no latency model | Fill-model realism |
| 10 | **P1** | Open | Post-trade markouts depend on real asyncio timing and mutable records | Determinism / analytics |
| 11 | **P1** | Open | Runtime infrastructure relies on process-global service locators | Isolation / testability |
| 12 | **P1** | Open | Exchange market-data classes mix transport supervision, protocol parsing, normalization, and state | Multi-exchange maintainability |
| 13 | **P1** | Open | `ApplicationBase` and `cli.py` own too many lifecycle/composition responsibilities | Runtime maintainability |
| 14 | **P1** | Open | Persistence pressure and failure policy are implicit | Operational safety |
| 15 | **P2** | Open | Historical replay materializes entire ranges and uses an unbounded process-global trade cache | Scale / memory |
| 16 | **P2** | Open | Exchange capabilities and symbol normalization are only partially centralized | Multi-exchange maintainability |
| 17 | **P2** | Open | `SQLiteWriter` has too many internal responsibilities | Maintainability |
| 18 | **P3** | Open | Runtime validation uses `assert` in several configuration paths | Robustness |
| 19 | **P3** | Open | Domain identifiers are represented mostly as plain strings/integers | Type safety |
| 20 | **P3** | Open | Several dashboard modules are growing large | UI maintainability |
| — | Constraint | — | Replayed historical markets cannot react to orders that were never actually present | Interpretation limit |

**Active P0 order after the current open work:** fee economics → fill identity → event sequencing/session isolation → order lifecycle/reconciliation.


---

# P0 — Blockers to trustworthy results or safe live trading

## 1. Kraken fee economics overwhelm the current quoted edge

### Problem

For the current BTC/USD experiment, the dominant problem is economic rather than architectural.

A simple maker earns approximately:

```text
gross edge per fill
    = quote distance from fair value × quantity
```

but pays:

```text
maker fee
    = maker fee rate × price × quantity
```

With BTC around `$100,000`, the current default quote size of `0.0005 BTC` is about `$50` notional.

At Kraken's higher retail maker-fee tiers, the fee can be much larger than the natural spread or the edge being requested by the strategy.

Approximate break-even quote distance per side is:

```text
break-even offset = maker fee rate × BTC price
```

At a `$100,000` BTC price:

| Maker fee | Approx. break-even offset |
|---:|---:|
| 0.40% | $400 |
| 0.30% | $300 |
| 0.22% | $220 |
| 0.10% | $100 |
| 0.00% | $0 |

BTC/USD normally trades much tighter than these values.

### Why it matters

This means widening the quote to cover a 30–40 bps fee does not transform the strategy into a competitive traditional market maker. It moves the order far from the touch and causes fills mainly when the market travels into or through the quote, which is exactly where adverse selection is strongest.

`FeeAwareQuoteOffsetService` is still useful because it makes the cost visible and prevents the engine from silently quoting below fee break-even. It does **not** remove the economic disadvantage.

Inventory or fair-value skew also cannot compensate if the fee component is hundreds of dollars while the directional adjustment is only a few dollars.

### Resolution

This issue is not primarily solved by code.

The realistic options are:

1. Reach a materially better maker-fee tier.
2. Trade a venue/product where effective maker fees are much lower.
3. Trade a pair whose natural opportunity is sufficiently wide relative to fees.
4. Develop predictive edge large enough to overcome fees and adverse selection.
5. Use the engine primarily for signal research until venue economics become viable.

### Acceptance criterion

Before declaring a strategy profitable, report at minimum:

```text
Gross spread/markout PnL
- maker/taker fees
- adverse-selection markout
= net expected edge
```

Gross and net markouts should remain visible separately.

---

## 2. Fill identity is not unique in the live Kraken path

### Problem

The Kraken execution path currently constructs fills with:

```python
Trade(
    trade_id=0,
    ...
)
```

while post-trade analysis keeps pending markout records keyed by `trade_id`.

Conceptually:

```python
pending_fills[trade.trade_id] = record
```

Therefore two live fills that occur before the prior fill's 30-second markout lifecycle completes can address the same entry.

This can corrupt:

- markout attribution
- decorated fill records
- fill-level PnL analysis
- partial-fill accounting

### Required design

Separate these identifiers explicitly:

```text
ClientOrderId
ExchangeOrderId
ExchangeTradeId
InternalFillId
```

The preferred `InternalFillId` should be stable and unique even if a venue has awkward identifiers.

For example:

```python
@dataclass(frozen=True)
class FillId:
    venue: Market
    exchange_order_id: str
    exchange_trade_id: str
```

or an internal UUID plus retained venue identifiers.

### Tests required

- two separate orders filling inside the same 30-second markout window
- two partial fills belonging to one order
- two fills with the same price/quantity/timestamp
- markout callbacks updating the correct fill
- restart/reconciliation retaining stable exchange identifiers

### Acceptance criterion

No post-trade, accounting, or persistence map should use a non-unique placeholder ID.

---

## 3. Event correctness depends on implicit subscriber ordering and a global signal namespace

### Problem

`SignalManager.connect_all()` discovers subscribers by iterating over `dir(self)`.

That indirectly determines subscription order from attribute names.

`ApplicationBase` currently documents an ordering dependency resembling:

```text
fair-price model
    before
PositionManager
    before
PostTradeService
```

and `PostTradeService` expects the position update for a fill to have happened before its own fill handler runs.

That means renaming an attribute can potentially change accounting behavior.

There is a second ownership issue: signal registration lives in a process-global namespace, and `disconnect_all()` disconnects receivers from that namespace globally.

Two application/session instances in one process can therefore interfere with one another.

### Why it matters

Event ordering is business logic. It should not be an accidental consequence of lexical attribute sorting.

The current model also makes these future directions risky:

- several symbols in one process
- multiple exchanges
- parallel sessions
- independent tests
- strategy hot-reload
- asynchronous event consumers

### Recommended near-term fix

Do **not** begin with a giant event-system rewrite.

First fix the concrete fill-accounting dependency:

```text
OrderFilled
    ↓
PositionManager
    ↓
AccountedFill(fill, position_before, position_after)
    ↓
PostTradeService
```

This eliminates the specific ordering dependency.

### Recommended long-term fix

Move to an application/session-owned event bus:

```python
class EventBus:
    def subscribe(self, event_type, handler): ...
    def publish(self, event): ...
    def close(self): ...
```

Prefer typed events over magic signal-name strings.

Each application owns its subscriptions and disconnects only those subscriptions.

### Acceptance criterion

- Renaming a component attribute cannot change event semantics.
- Two sessions can coexist in one process.
- Stopping one session cannot detach subscribers belonging to another.

---

## 4. Coordinated service health — addressed by PR #60

**Status:** Resolved by merged GitHub PR #60 (`feat: gate trading on service health`).

The original problem was that services initialized and recovered independently, with no authoritative in-memory answer to:

```text
MAY THIS SESSION SUBMIT A NEW ORDER NOW?
```

PR #60 implements the intended coordinated-health model rather than adding more strategy-specific readiness flags or a separate trading-readiness state.

### Implemented design

The PR introduces:

```text
HealthState
    INITIALIZING
    HEALTHY
    WARNING
    CRITICAL

Health
    one in-memory state per service

HealthMonitor
    aggregate trading health derived from participating services
```

The CLI creates one aggregate trading `HealthMonitor` and passes it to the
parameter service, strategy, application, market-data service, and execution
service. Each service registers its own health when it receives the monitor;
no separate registry or trading-critical flag is needed.

Conceptually:

```text
ParameterService.health ──────┐
                              │
MarketDataFeed.health ────────┼──→ HealthMonitor("trading")
                              │
ExecutionService.health ──────┘
                                      │
                                      ├──→ MarketMakingStrategy
                                      │      stop quoting / withdraw quotes
                                      │
                                      └──→ ExecutionService
                                             final order gate
```

### Service-owned healthy transitions

A service is no longer considered healthy merely because its object exists.

PR #60 makes each service responsible for declaring when its state is actually usable:

- parameters become healthy only after their initial usable state is available;
- Kraken market data waits for both the matching instrument rules and a synchronized book snapshot;
- Binance.US waits for its required instrument/book initialization;
- historical replay becomes healthy after its historical data is ready;
- warning issues remain visible while trading continues;
- critical reconnect/recovery and heartbeat issues stop trading immediately;
- the aggregate monitor permits trading again only when every participating service can trade: none is `INITIALIZING` or `CRITICAL`.

This replaces the former `require_instrument()` strategy hook with a general service-health contract shared by both exchanges.

### Strategy behavior

`MarketMakingStrategy` receives the aggregate trading health through its
constructor.

When aggregate health is `INITIALIZING` or `CRITICAL`:

```text
new quote generation stops
+
existing strategy quotes are withdrawn
```

New quote reservation uses `HealthMonitor.run_if_can_trade()` so local quote reservation is coordinated with the current health decision.

The order is still independently checked at the execution boundary.

### Execution-boundary behavior

Both mock execution and Kraken execution receive the same aggregate health and refuse new orders while it is initializing or critical.

That gives two gates:

```text
strategy authorization
        +
execution-boundary authorization
```

so a stale strategy decision alone cannot authorize an order.

### Health and heartbeat now share one lifecycle

`Heartbeater` owns a `Health` object.

Adding a warning heartbeat issue degrades the service without stopping trading. A critical issue blocks trading. Once the service has reached its usable state, clearing its final issue can restore health.

The operational heartbeat therefore reflects the same in-memory service condition that participates in trading authorization, instead of readiness and monitoring being separate concepts.

### What PR #60 resolves

The PR addresses the original coordinated-health issue:

- startup is gated;
- parameters participate in aggregate health;
- instrument/book initialization participates in aggregate health;
- dependency health loss stops new quoting;
- existing quotes are withdrawn on aggregate health loss;
- execution performs a final health check;
- recovery resumes trading after every service leaves initializing or critical health;
- historical replay has an explicit healthy transition;
- order-authorization policy is centralized instead of spreading venue-specific booleans through strategy code.

The issue remains here as a record of the resolved safety boundary.

### What PR #60 does **not** resolve

This is not the same as authoritative exchange order lifecycle management.

Health-triggered withdrawal still uses the existing `_cancel()` lifecycle, so the broader problem remains:

```text
cancel requested
≠
cancel confirmed by venue
```

A delayed or failed cancellation can still require explicit reconciliation.

That remains part of **Issue 5 — QuotePlanner / OrderReconciler / explicit order states** and stays P0.

This PR also does not solve **Issue 3**, the global signal namespace and implicit subscriber-order problem.

### Follow-up

No separate readiness state, registry, or coordinator project is needed after PR #60 merges.

Future work should be incremental:

- pass the shared `HealthMonitor` to each service whose health must affect trading;
- preserve service-owned initialization/recovery semantics;
- expose richer health reasons if operational diagnosis needs them;
- keep execution authorization based on current in-memory health;
- add venue-specific recovery tests as new adapters are introduced.

---

## 5. Strategy owns desired quotes and assumed live-order state in one object

### Problem

`MarketMakingStrategy` currently owns both:

### Trading decision responsibilities

- market snapshot construction
- fair-price calculation
- quote offsets
- parameter lookup
- inventory checks
- size validation
- price rounding
- requote tolerance

and:

### Execution lifecycle responsibilities

- current live orders
- client-order IDs
- cancel decisions
- cancel emission
- order creation
- assumptions about whether orders remain working

A particularly important lifecycle problem is that cancel intent and confirmed cancellation are not the same state.

If strategy code removes a working order from its local map when it merely **requests** cancellation, a failed or delayed cancel can produce a phantom live order at the exchange.

The same applies to:

- rejected new orders
- delayed acknowledgements
- partial fills
- reconnects
- order-status reconciliation

### Recommended split

#### `QuotePlanner`

Pure desired-state logic:

```python
QuotePlan plan(
    market: MarketSnapshot,
    position: Position,
    parameters: MarketMakingParameters,
) -> QuotePlan:
    ...
```

Output:

```python
@dataclass(frozen=True)
class QuotePlan:
    bid: DesiredQuote | None
    ask: DesiredQuote | None
```

No exchange IDs and no assumptions about actual venue state.

#### `OrderReconciler`

Owns the difference between:

```text
desired order state
vs.
confirmed venue order state
```

Example state machine:

```text
PENDING_NEW
WORKING
PENDING_CANCEL
PARTIALLY_FILLED
FILLED
REJECTED
CANCELLED
UNKNOWN / RECONCILING
```

#### `ExecutionPort`

Exchange-neutral interface:

```python
class ExecutionPort(Protocol):
    async def submit(self, request: OrderRequest) -> OrderAck: ...
    async def cancel(self, order: WorkingOrder) -> CancelAck: ...
```

### Acceptance criterion

Strategy code can be tested as pure quote-generation logic without an exchange, and a cancellation failure does not cause the internal state to pretend the order disappeared.

---

## 6. Simulated queue position is effectively zero for the quotes actually placed

**Status:** Addressed in GitHub PR #61; pending merge.

### Problem

The mock resting-order model initializes `ahead_quantity` from the BBO only when the simulated order price exactly equals the current best bid/ask.

The strategy often quotes well behind the touch, especially after fees are added.

For those prices, simulated `ahead_quantity` remains zero.

The simulator therefore effectively assumes:

```text
we arrive first at our price level
```

even though an actual book can contain substantial resting size there.

### Why it matters

This likely causes the largest optimistic error in current paper-fill frequency.

A strategy can appear to receive many fills because its simulated queue position is unrealistically favorable.

This directly undermines conclusions such as:

- expected fill rate
- spread capture
- turnover
- realized fee burden
- inventory distribution
- total PnL

### Near-term fix

If L2 depth contains the quoted level:

```text
initial ahead quantity
≈ resting quantity already present at that price
```

That is much better than zero.

### Remaining uncertainty

L2 still cannot tell which cancellations happened:

```text
ahead of us
or
behind us
```

once we join a level.

An exchange L3 feed would provide much better queue information. Its normalized
events must retain individual order identity; an L3 book can derive the shared
L2 `OrderBook`, but the recording must not collapse the original L3 data.

### Acceptance criterion

Paper orders away from the touch must not default to first-in-queue when visible depth exists at their price.

---

# P1 — Important realism, safety, and architecture work

## 7. Replay cannot support the better fill model because full book state is not recorded

**Status:** Addressed in GitHub PR #61; pending merge.

### Problem

The engine now has live book depth, but historical replay does not preserve enough information to reconstruct the evolving book.

Current recording focuses on trades and selected book features such as:

- BBO
- imbalance
- depth-weighted metrics

Those are useful signals but insufficient to reproduce queue/depth consumption for a more realistic fill simulator.

This creates an undesirable asymmetry:

```text
live paper
    potentially gets realistic fills

replay
    keeps simplistic fills
```

Yet replay is where weeks of data can be evaluated quickly.

### Recommended direction

Record a compact reconstructable order-book stream.

A useful format could be:

```text
initial snapshot
+
incremental level updates
+
sequence/checksum metadata
```

It does not need to record a giant full-book snapshot on every tick.

Then both live paper and replay use the same execution simulator.

### Acceptance criterion

A recorded session can rebuild the L2 book closely enough for the fill simulator to make the same depth/queue decisions offline.

---

## 8. Sweep fills are not sized from consumed depth

### Problem

When a market trade prints beyond a resting simulated quote, the mock treats the quote level as crossed.

The fill is capped by the print quantity, but the simulator does not model how much liquidity between the touch and our level was consumed first.

Example:

```text
ask touch             100.00
better liquidity      100.01 .. 100.09
our sell quote        100.10
trade print quantity  3 BTC
```

Not all 3 BTC is necessarily available to fill us; some volume first consumed better-priced orders.

### Recommended fix

Use current book depth to calculate:

```text
aggressive quantity
- quantity consumed at better prices
= quantity capable of reaching our quote
```

Then cap simulated fill quantity accordingly.

### Dependency

This is naturally paired with:

- book-aware paper execution
- replayable book recording

### Acceptance criterion

A sweep cannot fill more simulated quantity at our price than the observed aggressive volume remaining after better levels are consumed.

---

## 9. Paper/replay execution has no latency model

### Problem

Currently, an order can conceptually be:

```text
decision made
→ immediately resting
```

Real trading experiences:

```text
market-data latency
+
strategy compute
+
outbound network
+
exchange gateway/matching engine
+
acknowledgement latency
```

Queue position should reflect arrival time at the venue, not decision time locally.

### Why it matters

Even a small latency moves the simulated order behind other orders that join the same level during the delay.

Latency also changes adverse-selection behavior because the quote may be stale by the time it rests.

### Recommended model

Start simple and explicit:

```python
@dataclass(frozen=True)
class LatencyModel:
    market_data_ms: float
    outbound_order_ms: float
    cancel_ms: float
```

Later, replace constants with empirical distributions measured from live sessions.

### Acceptance criterion

Paper/replay orders become active only after simulated arrival time, and cancels remain exposed until simulated cancellation arrival.

---

## 10. Post-trade markouts depend on real asyncio timing and mutable records

### Problem

The post-trade service schedules markouts with real event-loop timing:

```text
100 ms
1 s
5 s
30 s
```

and progressively mutates one `DecoratedOrderFill`, re-emitting the whole record.

This couples analytical semantics to:

- asyncio
- wall/event-loop timing
- persistence upsert behavior

### Recommended direction

Introduce a scheduler abstraction:

```python
class Scheduler(Protocol):
    def call_at(self, timestamp, callback): ...
```

Implementations:

```text
LiveScheduler     → asyncio
ReplayScheduler   → simulated event time
FakeScheduler     → unit tests
```

Also consider immutable analytical events:

```text
FillRecorded
FillMarkoutMeasured(fill_id, horizon=100ms, fair_price=...)
FillMarkoutMeasured(fill_id, horizon=1s, fair_price=...)
...
```

Persistence can materialize them into the current wide table if desired.

### Acceptance criterion

A unit test can advance a fake clock through all markout horizons without `sleep()`, and replay results are deterministic.

---

## 11. Runtime infrastructure relies on process-global service locators

### Problem

`parameter_service()` exposes a module-global parameter service, changed through `use_parameter_service()`.

Other runtime concepts follow similar global-access patterns, including time/ID infrastructure.

This makes infrastructure easy to access but hides dependencies.

### Costs

- test state can leak
- parallel sessions are difficult
- multiple exchanges/symbols in one process become risky
- replay substitution is less explicit
- dependency ownership is unclear

### Recommended design

Introduce an application-owned context:

```python
@dataclass(frozen=True)
class EngineContext:
    events: EventBus
    parameters: IParameterService
    clock: Clock
    scheduler: Scheduler
    ids: IdGenerator
    health: HealthReporter
```

Not every object needs the entire context. Inject the smallest dependency practical.

### Migration strategy

Do this incrementally.

Do **not** rewrite all global infrastructure in one PR.

A useful sequence is:

```text
EventBus
→ Scheduler
→ ParameterService
→ Clock / IDs
```

### Acceptance criterion

A second session can be constructed with independent parameters, clock, event subscriptions, and IDs without changing process-global state.

---

## 12. Exchange market-data classes mix transport, protocol, normalization, and state

### Problem

A venue public-feed class such as Kraken currently owns many concerns:

- websocket creation
- reconnect loops
- retry policy
- subscription requests
- JSON parsing
- Kraken message semantics
- checksum behavior
- order-book reconstruction
- BBO state
- instruments
- event dispatch
- health issues

Binance.US needs many of the same transport concerns.

### Recommended decomposition

```text
WebSocketSupervisor
    connect / reconnect / cancellation / backoff

KrakenProtocol
    subscribe messages / decode JSON / validate checksums

MarketDataNormalizer
    venue DTO → Trade / BookUpdate / InstrumentSpec

OrderBookAssembler
    snapshot + incremental state

PublicFeed
    composes the above and publishes domain events
```

The generic transport supervisor can be reused across venues while protocol behavior remains venue-specific.

### Acceptance criterion

Protocol decoder tests can process captured JSON fixtures without opening a socket.

---

## 13. `ApplicationBase` and `cli.py` own too many lifecycle/composition responsibilities

### `ApplicationBase` currently covers

- dependency composition
- path preparation
- logging setup
- global parameter installation
- signal connection
- persistence lifecycle
- market-data thread lifecycle
- replay lifecycle
- shutdown
- session output

### `cli.py` currently covers

- argument parsing
- mode validation
- signal handling
- monitoring configuration
- exchange capability checks
- replay selection
- parameter-store selection
- profiler setup
- strategy construction
- fair-price construction
- application construction
- runtime execution

### Recommended target

```text
CLI
    ↓ parses
SessionConfig
    ↓
SessionFactory
    ↓ builds
TradingSession
    ↓
SessionRunner / EngineRuntime
```

Example:

```python
config = parse_args()
session = session_factory.create(config)
result = await runner.run(session)
```

### Important rule

Keep strategy composition out of the CLI.

The CLI should decide **what** to run, not instantiate the details of every adjustment model.

### Acceptance criterion

A test can construct and run a session from a `SessionConfig` without calling argparse or mutating CLI globals.

---

## 14. Persistence pressure and failure policy are implicit

### Problem A — unbounded queue

`SQLiteWriter` uses an unbounded `SimpleQueue`.

If disk throughput falls below producer throughput for a sustained interval, queued data can grow without a defined memory ceiling.

### Problem B — all records effectively share one persistence policy

A failed SQLite batch is rolled back and dropped, with the error surfaced later.

Dropping may be acceptable for some analytics, but not necessarily for:

```text
order state
fills
positions
risk/audit events
```

### Recommended design

Classify records:

```text
CRITICAL
    orders
    acknowledgements
    cancels
    fills
    positions
    risk-state transitions

BEST_EFFORT
    book features
    debug telemetry
    derived analytics
```

Then define overload/failure behavior separately.

Also expose:

```text
queue depth
oldest queued age
writer throughput
dropped best-effort rows
last persistence error
```

through health monitoring.

### Acceptance criterion

The engine has a documented behavior when SQLite cannot keep up, and critical accounting records are not silently treated the same as optional telemetry.

---

# P2 — Scaling and maintainability

## 15. Historical replay materializes entire ranges and uses an unbounded process-global trade cache

### Problem

`DatabaseDataSource.download_market_trades()`:

1. loads the selected SQL range into a Pandas DataFrame
2. converts the full result into a Python list of `Trade`
3. stores the list in a class-level cache

The cache has no eviction.

Long recordings and many replay windows can therefore retain increasing memory.

### Recommended API

```python
async for batch in source.iter_trades(
    symbol,
    start,
    end,
    batch_size=10_000,
):
    ...
```

Possible cache strategies:

- no cache for SQLite-backed replay
- session-local cache
- bounded LRU
- cache compact serialized blocks rather than object lists

### Acceptance criterion

Replay memory usage is approximately bounded by batch size rather than total requested history.

---

## 16. Exchange capabilities and symbol normalization are only partially centralized

### Problem

`ExchangeDefinition` is already a useful registry, but exchange knowledge still leaks into:

- CLI logic
- application classes
- symbol conversion
- feature availability checks

### Recommended evolution

```python
class ExchangeAdapter(Protocol):
    market: Market
    capabilities: ExchangeCapabilities

    def canonical_symbol(self, raw: str) -> Symbol: ...
    def wire_symbol(self, symbol: Symbol) -> str: ...
    def create_market_data(self, ctx): ...
    def create_execution(self, ctx): ...
    def fee_schedule(self): ...
```

Capabilities:

```python
@dataclass(frozen=True)
class ExchangeCapabilities:
    live_execution: bool
    public_market_data: bool
    remote_history: bool
    instrument_metadata: bool
```

### Acceptance criterion

Adding a third exchange primarily requires adding one adapter package and registry entry, rather than editing strategy and CLI internals.

---

## 17. `SQLiteWriter` has too many internal responsibilities

### Problem

The class currently owns:

- queueing
- worker-thread lifecycle
- connection setup
- batching
- schema inspection
- schema creation
- schema widening
- upserts
- pruning
- error transport
- shutdown

The public abstraction is fine, but the internal class is becoming a subsystem.

### Recommended internal decomposition

```text
SQLiteWriter
├── WriterWorker
├── SQLiteSchemaManager
└── SQLiteRowStore
```

This can preserve the existing public API.

### Acceptance criterion

Persistence schema behavior can be tested separately from queue/thread behavior.

---

# P3 — Cleanup and quality improvements

## 18. Runtime validation uses `assert` in configuration paths

### Problem

`assert` is appropriate for impossible programmer states, but not user/configuration validation.

Assertions may be disabled under optimized Python execution.

Examples to avoid:

```python
assert api_key
assert valid_cli_combination
assert parameter_within_bounds
```

### Replace with

- `parser.error(...)`
- `ConfigurationError`
- `ValueError`
- typed validation errors

### Acceptance criterion

Invalid runtime configuration produces explicit errors regardless of Python optimization settings.

---

## 19. Domain identifiers are mostly primitive strings/integers

Important concepts include:

```text
symbol
client order ID
exchange order ID
exchange trade ID
fill ID
```

Representing all of these as primitives increases the chance of accidental mixing.

Use lightweight value types where they improve clarity:

```python
@dataclass(frozen=True)
class ClientOrderId:
    value: str
```

Do not overdo this for every scalar; focus on identifiers that cross subsystem boundaries.

---

## 20. Several dashboard modules are growing large

Files such as the order/PnL and parameter pages contain significant query, transformation, and rendering logic.

After engine work stabilizes, split UI code along:

```text
queries/
view_models/
components/
pages/
```

This is deliberately low priority because UI module size is not currently a trading-correctness problem.

---

# Known constraint — historical replay cannot model market reaction to our nonexistent orders

This issue should remain documented, but it is not a normal refactoring task.

Historical replay uses the market that actually occurred.

Our hypothetical quote was not present in that market.

Therefore replay cannot know how other participants would have reacted to it.

For example:

```text
Would someone have cancelled because our quote appeared?
Would a taker have routed differently?
Would another maker have repriced?
Would our displayed size have attracted or repelled flow?
```

No amount of L2/L3 historical reconstruction can answer those counterfactual questions perfectly.

A better fill simulator can improve:

- queue position
- latency
- depth consumption
- partial fills

but historical replay remains a **counterfactual approximation**.

Treat this as an interpretation constraint rather than something that blocks the architecture roadmap.

---

# Target architecture

A useful direction is:

```text
                          SessionConfig
                               │
                               ▼
                         SessionFactory
                               │
                               ▼
                       ┌──────────────┐
                       │TradingSession│
                       └──────┬───────┘
                              │
                    ┌─────────▼──────────┐
                    │    EngineContext   │
                    │ events / clock     │
                    │ scheduler / params │
                    │ HealthMonitor / IDs│
                    └─────────┬──────────┘
                              │
        ┌─────────────────────┼───────────────────────┐
        ▼                     ▼                       ▼
 MarketDataAdapter       QuotePlanner            PositionManager
        │                     │                       │
        ▼                     ▼                       ▼
   MarketState          Desired Quotes            AccountedFill
                              │                       │
                              ▼                       ▼
                       OrderReconciler         PostTradeService
                              │
                              ▼
                        ExecutionPort
                              │
                              ▼
                       Exchange Adapter
```

The important boundaries are:

```text
Strategy decides what it wants.
Order reconciler knows what is actually working.
Execution adapter knows how the venue works.
Position manager owns accounting.
Post-trade analytics consumes accounted fills.
Runtime owns readiness, time, scheduling, and events.
```

---

# Recommended implementation roadmap

## Phase 0 — Establish baselines

Before architectural changes:

- keep current tests green
- capture a representative paper session
- save representative replay outputs
- record fill count, position path, gross/net PnL, and markouts

This creates behavioral references for subsequent PRs.

---

## Phase 1 — Fix data/accounting correctness

### PR 1 — Unique fill identity

Implement:

- unique internal `FillId`
- exchange order/trade IDs where available
- post-trade keyed by `FillId`
- partial-fill tests

**Resolves:** Issue 2.

---

### PR 2 — Deterministic accounted-fill pipeline

Change:

```text
order_fill
 ├── PositionManager
 └── PostTradeService
```

to:

```text
order_fill
    ↓
PositionManager
    ↓
AccountedFill(fill, before, after)
    ↓
PostTradeService
```

Do this before a full EventBus replacement.

**Partially resolves:** Issue 3.

---

### PR 3 — Session-scoped event ownership

Introduce session-owned subscriptions.

Remove global `disconnect_all()` behavior.

Add a test running two sessions in one process.

**Completes the core of:** Issue 3.

---

## Phase 2 — Make live order state authoritative

### PR 4 — QuotePlanner extraction

Move pure logic out of `MarketMakingStrategy`:

- fair value
- offsets
- inventory restrictions
- desired quote size/price
- venue rounding constraints

Return `QuotePlan`.

---

### PR 5 — OrderReconciler and explicit acknowledgements

Add:

- working-order state machine
- new-order acknowledgement
- rejection
- cancel acknowledgement
- cancel rejection/failure
- partial fills
- unknown/reconcile state

**Resolves the main architecture of:** Issue 5.

---

### ~~PR 6 — Coordinated service health~~ → Implemented in GitHub PR #60

**Status:** Resolved; PR #60 is merged.

Implemented:

- per-service `Health`;
- aggregate `HealthMonitor`;
- `INITIALIZING` / `HEALTHY` / `WARNING` / `CRITICAL` lifecycle;
- venue-specific healthy transitions;
- warning/critical health propagation and recovery;
- quote withdrawal on health loss;
- guarded strategy quote reservation;
- final execution-side order gating;
- heartbeat integration;
- replay health initialization.

**Resolved:** Issue 4.

Do **not** fold order acknowledgement or cancel acknowledgement into this item; those remain Issue 5.

---

## Phase 3 — Make strategy research believable

### ~~PR 7 — Book-aware initial queue position~~ → Implemented together in GitHub PR #61

Use visible L2 quantity at the order level instead of default zero.

**Resolves most of:** Issue 6.

---

### PR 8 — Depth-aware sweep fills

Feed order-book state into paper execution and cap sweep fills from consumed depth.

**Resolves:** Issue 8.

---

### PR 9 — Latency simulation

Model order/cancel arrival times.

Start with configurable constants; later calibrate from live measurements.

**Resolves:** Issue 9.

---

### ~~PR 10 — Record reconstructable book updates~~ → Implemented together in GitHub PR #61

Persist compact book snapshot/delta data and replay it through the same book builder.

**Resolves:** Issue 7 and makes PRs 7–9 useful in replay.

---

## Phase 4 — Deterministic runtime and analytics

### PR 11 — Scheduler abstraction

Make markouts use live/replay/fake schedulers.

Move toward immutable markout measurement events.

**Resolves:** Issue 10.

---

### PR 12 — EngineContext

Begin replacing global runtime locators with session-owned dependencies.

Start with:

```text
events
scheduler
parameters
clock
IDs
```

**Resolves:** Issue 11.

---

## Phase 5 — Exchange architecture

### PR 13 — WebSocket transport supervisor

Extract reconnect/cancellation/backoff infrastructure.

---

### PR 14 — Venue protocol decoder/normalizer

Move Kraken protocol parsing and book normalization behind adapter boundaries.

---

### PR 15 — Complete ExchangeAdapter capability model

Centralize symbol rules, constructors, and supported features.

**Resolves:** Issues 12 and 16.

---

## Phase 6 — Runtime and persistence scaling

### PR 16 — Simplify CLI/Application composition

Add:

```text
SessionConfig
SessionFactory
SessionRunner
```

**Resolves:** Issue 13.

---

### PR 17 — Persistence classes and backpressure

Add:

- bounded pressure strategy
- queue metrics
- critical vs best-effort persistence
- clear write-failure semantics

**Resolves:** Issue 14.

---

### PR 18 — Streaming replay

Move replay data APIs toward iterators/batches and remove/unbound the global cache.

**Resolves:** Issue 15.

---

### PR 19 — Internal SQLite decomposition

Extract schema/row/thread responsibilities as useful.

**Resolves:** Issue 17.

---

# Test plan

The following tests are more important than package reshuffling.

## Correctness

### Fill identity

```text
two orders fill during one 30-second markout window
→ both records survive independently
```

### Partial fills

```text
one order
→ fill A
→ fill B
→ distinct FillIds
→ correct aggregate position
```

### Event-order independence

Rename or reorder component attributes.

Expected result:

```text
identical accounting and post-trade output
```

### Session isolation

Run two sessions.

Stop one.

Expected:

```text
other session remains fully subscribed
```

### Cancel failure

```text
working order
→ cancel requested
→ venue cancel fails
→ engine still considers order potentially working
```

### Rejection

```text
desired quote
→ submit
→ rejected
→ no phantom working order
```

### Readiness race

```text
strategy calculates quote while READY
→ dependency becomes critical
→ execution boundary refuses new order
```

---

## Simulation validity

### Queue-position test

Quote behind touch at a price with visible resting quantity.

Expected:

```text
ahead_quantity > 0
```

### Sweep test

Aggressive print crosses several levels.

Expected:

```text
our fill <= aggressive quantity remaining after better levels
```

### Latency test

Order decision at `t`.

Configured outbound latency `L`.

Expected:

```text
order cannot fill before t + L
```

### Replay/live consistency

Record a short book/trade sequence and feed it through:

```text
live paper simulator
and
historical replay simulator
```

Expected:

```text
same simulated decisions for the same event stream
```

---

## Determinism

### Markout scheduler

Use fake time:

```text
advance to 99ms  → no 100ms markout
advance to 100ms → markout emitted
...
advance to 30s   → final markout emitted
```

No real sleeps.

---

## Persistence

### Slow disk

Artificially delay writer.

Verify:

- queue health becomes degraded
- defined backpressure/drop policy activates
- critical records follow their guaranteed policy

---

# What not to refactor yet

Avoid spending significant time on the following before P0/P1 issues are controlled:

- generic strategy plugin frameworks
- microservices
- replacing SQLite solely because the project may grow
- rewriting fair-value adjustment classes that are already cohesive
- splitting every large file based only on line count
- changing async frameworks
- supporting many symbols in one process before session/event ownership is fixed
- sophisticated L3 simulation before a correct L2 model exists

---

# Relationship to strategy research

Architecture and alpha research should remain separate concepts.

A good engine cannot make an unprofitable venue/fee combination profitable.

Likewise, a statistically promising fair-price signal is not proven by a simulator with unrealistic queue position.

Use three distinct measurements:

```text
1. Signal quality
   future fair-price movement / gross markout

2. Execution quality
   realistic fill probability + adverse selection

3. Economics
   execution edge - fees
```

A useful research result can therefore be:

```text
signal has positive gross markout
but
current Kraken fee tier makes net execution unprofitable
```

That is still valuable information and should not be confused with a failed signal.

---

# Change log

## 2026-09-15 — Depth-aware paper execution and replay implemented

- initialized simulated queue ahead from L2 quantity at the exact order price;
- introduced a per-order `QueuePosition` initialized as the best guess from
  available market data;
- added compact, versioned, model-labelled L2 snapshot/delta records;
- rebuilt and published the shared `OrderBook` during local replay;
- retained trade-only replay for legacy recordings;
- kept L3 as a distinct future normalized event that can derive an L2 view
  without losing order identity.

---

## 2026-09-15 — PR #60 coordinated-health design updated

Reviewed GitHub PR #60, `feat: gate trading on service health`.

Changes to this roadmap:

- marked Issue 4 **Addressed — pending merge**;
- removed the coordinated-health issue from the active P0 ordering;
- documented the concrete `Health` / `HealthMonitor` design;
- documented service-owned initialization and recovery;
- documented quote withdrawal and execution-boundary gating;
- retained cancellation acknowledgement/reconciliation under Issue 5;
- changed the future readiness roadmap item into an implemented coordinated-health item;
- documented that constructor injection determines which services participate;
- documented that `WARNING` allows trading while `INITIALIZING` and `CRITICAL` block it.

---

# Overall assessment

The engine has reached a useful transition point.

The existing architecture already has sensible conceptual modules:

- market data
- execution
- position
- post-trade
- risk
- strategy
- parameters
- persistence
- exchange definitions

The primary problem is not the directory tree. It is that some important boundaries are still implicit:

```text
event order is implicit
session ownership is global
working-order state is optimistic
fill identity is incomplete
paper fills are optimistic
replay data is too thin for realistic execution

service health now gates trading through the shared `HealthMonitor` in PR #60
```

The best path is therefore **incremental**:

```text
correct accounting
→ authoritative order lifecycle
→ coordinated service health
→ realistic fill simulation
→ replayable book state
→ explicit runtime context
→ cleaner exchange adapters
→ scaling/cleanup
```

That sequence improves both research credibility and live-trading safety without stopping strategy development for a large rewrite.
