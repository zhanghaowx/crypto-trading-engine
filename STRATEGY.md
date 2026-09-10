# Strategy

Three initiatives: (1) a `PostTradeService` that records a
`decorated_order_fill` for every fill, replacing the dashboard's current
fill display, (2) a per-fill PnL breakdown (spread capture + markout PnL −
fees) built from that data, and (3) a new `Fair = Mid + αSignal` pricing
model with several alpha signals added incrementally.

Parts 1 and 2 below are detailed enough to implement directly. Part 3 needs
its own scoping pass (most of its signals — order-flow imbalance,
cross-venue price — need new market data plumbing, e.g. an L2 order book
feed for Kraken, that doesn't exist yet) and is left as a short follow-up
outline at the end.

Inventory tracking is sourced via a new `position_updated` signal from
`PositionManager` rather than having `PostTradeService` duplicate position
accounting.

## How this fits the existing architecture

Everything here reuses existing machinery — no new persistence or dashboard
plumbing is needed:

- Fills already flow as `Trade` over the blinker `"order_fill"` signal
  (`jolteon/market_data/core/trade.py`, emitted from
  `jolteon/execution/kraken/execution_service.py` and the mock execution
  services).
- `SignalRecorder` (`jolteon/core/event/signal_recorder.py`) persists *any*
  signal's payload into a same-named SQLite table automatically, via the
  background-thread `SQLiteWriter` (`jolteon/core/sqlite_writer.py`) — so
  emitting a new `"decorated_order_fill"` signal is all that's needed to get
  a `decorated_order_fill` table.
- `SQLiteWriter` already supports upsert-by-key: a payload class with a
  `PRIMARY_KEY` attribute causes later sends with the same key to `UPDATE`
  the existing row (`sqlite_writer.py:289-316`). This is exactly what's
  needed to fill in `fair_price_100ms/1s/5s/30s` as each horizon elapses
  after the initial fill record. No prior payload class uses `PRIMARY_KEY`
  yet — this will be the first.
- The dashboard's `read_table()` (`jolteon/app/data.py:41-99`) already
  special-cases primary-keyed tables (`_has_primary_key`, line 59): it
  re-reads the whole table each refresh instead of cursoring by rowid,
  specifically because a keyed row can be rewritten in place. **No changes
  needed there.**
- Fair price today is `MidPriceFairPriceModel` (mid of `BBO`) behind
  `IFairPriceModel.calculate(FairPriceContext)`
  (`jolteon/strategy/market_making/fair_value/`). Three changes: `calculate()`
  returns a `FairPrice(bid, ask)` pair instead of a single float, since a
  future model may legitimately want a different fair value on each side
  (e.g. inventory skew) even though today's mid-price model sets both to
  the same value (1a); it becomes a template method that emits a new
  `fair_price` signal on every call (also 1a); and `PostTradeService`
  shares one model instance with the strategy instead of defaulting to its
  own (1b) — so that a future, more complex model (Part 3) has one place to
  hook into, and so `fair_price` history stays one consistent series rather
  than mixing two instances' values.

## Part 1: `PostTradeService` + `decorated_order_fill`

### 1a. `IFairPriceModel` returns `FairPrice(bid, ask)` and emits a `fair_price` signal

`jolteon/strategy/market_making/fair_value/fair_price_model.py` — add a
`FairPrice` dataclass and turn `calculate()` into a template method so
every model gets signal emission for free, without each subclass
remembering to emit:

```python
@dataclass
class FairPrice:
    bid: float
    ask: float


class IFairPriceModel(ABC):
    def __init__(self):
        self.fair_price_event = signal("fair_price")

    def calculate(self, context: FairPriceContext) -> FairPrice:
        fair_price = self._calculate(context)
        self.fair_price_event.send(
            self.fair_price_event,
            symbol=context.bbo.symbol,
            bid_fair_price=fair_price.bid,
            ask_fair_price=fair_price.ask,
        )
        return fair_price

    @abstractmethod
    def _calculate(self, context: FairPriceContext) -> FairPrice:
        raise NotImplementedError
```

`MidPriceFairPriceModel` renames its existing `calculate` method to
`_calculate` and returns `FairPrice(bid=mid, ask=mid)` — both sides equal,
since it has no reason to skew. `test_mid_price_model.py` needs updating
for the new return type, plus a new assertion that the signal fires.

`MarketMakingStrategy.on_bbo` (`market_making_strategy.py:86-92`) is the
one existing caller of `calculate()`, and needs a small update since the
return type changed from `float` to `FairPrice`:

```python
fair_price = self._fair_price_model.calculate(FairPriceContext(bbo=bbo))
self._requote(MarketSide.BUY, fair_price.bid - self._half_spread)
self._requote(MarketSide.SELL, fair_price.ask + self._half_spread)
```

With today's symmetric `MidPriceFairPriceModel`, `fair_price.bid ==
fair_price.ask`, so quoting behavior is unchanged — this only starts to
matter once an asymmetric model exists.

This gives a `fair_price` SQLite table (columns: `symbol`,
`bid_fair_price`, `ask_fair_price`) via `SignalRecorder` for free,
populated whenever *any* consumer (the strategy, `PostTradeService`, later
a backtester) asks the model for a price, with no per-call-site emission
code needed. It also means any future fair price model automatically
participates, without having to remember to emit.

Because `signal("fair_price")` is global by name, two independently
constructed model instances would both write into the same table. That's
harmless while every model is a plain mid-price, but would silently mix
two different fair-price definitions once a more complex model exists —
which is why sharing one instance (1b) is necessary, not just tidy.

### 1b. Share one `IFairPriceModel` instance between strategy and `PostTradeService`

- `PostTradeService.__init__` takes an optional
  `fair_price_model: IFairPriceModel | None = None` (as already planned in
  1d below), defaulting to its own `MidPriceFairPriceModel()` only when
  nothing is supplied — e.g. when no strategy is attached.
- `jolteon/app/base.py` — `ApplicationBase.__init__` gains a new optional
  `fair_price_model: object = None` parameter, threaded straight through
  to `PostTradeService(fair_price_model=fair_price_model)`. Same pattern as
  the existing `strategy: object = None` parameter: `ApplicationBase`
  never inspects it, so wiring stays generic. `KrakenApplication` and
  `CoinbaseApplication` (`jolteon/app/kraken.py`, `jolteon/app/coinbase.py`)
  add the same passthrough parameter, mirroring how they already pass
  `strategy` through to `super().__init__`.
- `jolteon/cli.py` becomes the one place that constructs a single
  `MidPriceFairPriceModel()` and passes it to *both*
  `MarketMakingStrategy(symbol=strategy_symbol, fair_price_model=fair_price_model)`
  and `Application(..., fair_price_model=fair_price_model)`, right next to
  where `strategy` itself is built in the `--paper` branch.

### 1c. `PositionManager` emits `position_updated`

`jolteon/position/position_manager.py` — add a `PositionUpdate` dataclass
next to `Position`, holding just the symbol and its resulting position:

```python
@dataclass
class PositionUpdate:
    symbol: str
    volume: float
```

In `PositionManager.__init__`, add
`self.position_updated_event = signal("position_updated")` (same pattern as
`MarketMakingStrategy.__init__` uses for `order_event`). In `on_fill`
(lines 44-51), after applying the fill, send `position_updated_event` with
`PositionUpdate(symbol=trade.symbol, volume=self._position_for(trade.symbol).volume)`
— the position as it stands right after this fill. This is the only change
to this file — existing PnL/position accounting is untouched.

### 1d. New `decorated_order_fill` payload + `PostTradeService`

New module `jolteon/post_trade/decorated_order_fill.py`:

```python
@dataclass
class DecoratedOrderFill:
    PRIMARY_KEY = "trade_id"
    trade_id: int
    transaction_timestamp: datetime
    symbol: str
    side: MarketSide
    fill_price: float
    fill_qty: float
    fair_price_at_fill: float
    fee: float
    inventory_before: float
    inventory_after: float
    fair_price_100ms: float | None = None
    fair_price_1s: float | None = None
    fair_price_5s: float | None = None
    fair_price_30s: float | None = None
```

`fair_price_at_fill` and each horizon field stay a single column rather
than splitting into bid/ask variants: each is computed as the midpoint
`(fair_price.bid + fair_price.ask) / 2` of the model's `FairPrice` at that
moment. Bid/ask asymmetry (1a) affects quoting only; PnL decoration always
works off one blended number.

New module `jolteon/post_trade/post_trade_service.py` —
`PostTradeService(SignalSubscriber)`:

- Constructor takes an optional `fair_price_model: IFairPriceModel | None`
  (defaults to its own `MidPriceFairPriceModel()` per 1b above — normally
  the caller passes the same instance the strategy uses), and creates
  `self.decorated_order_fill_event = signal("decorated_order_fill")`.
- `@subscribe("ticker_feed") on_bbo` — caches the latest `BBO` per symbol
  (same pattern `PositionManager.on_bbo` already uses for mark prices), so a
  fair price can be computed on demand.
- `@subscribe("position_updated") on_position_updated` — `PositionUpdate`
  only carries the resulting volume, so `PostTradeService` derives
  inventory_before/after itself from two consecutive snapshots: it keeps
  `self._latest_volume: dict[str, float]`, and on each update stashes
  `(self._latest_volume.get(symbol, 0.0), position_update.volume)` as the
  pending before/after pair for that symbol before overwriting the cache
  with the new volume.
- `@subscribe("order_fill") on_fill` — builds the `DecoratedOrderFill` from
  the `Trade`, the pending before/after pair recorded for its symbol, and
  the midpoint of the current cached `BBO`'s `FairPrice` for
  `fair_price_at_fill`. Skips (no-op) if no `BBO` has been seen yet for
  that symbol. This relies on `PositionManager`'s `order_fill` receiver
  running — and emitting `position_updated` — before `PostTradeService`'s
  own; that holds because `ApplicationBase.__init__` constructs
  `self._position_manager` before `self._post_trade_service` and
  `SignalManager.connect_all()` connects signal subscribers in `dir(self)`
  order, which is alphabetical (`_position_manager` sorts before
  `_post_trade_service`) — worth a one-line comment in the code calling
  out this ordering dependency, since it's not obvious from either class
  alone. Keeps the finished record in an in-memory
  `dict[trade_id, DecoratedOrderFill]`, sends it over
  `decorated_order_fill_event`, and schedules four callbacks — at 0.1s, 1s,
  5s, 30s — via `asyncio.get_running_loop().call_later` (this runs on the MD
  thread's own event loop per `ApplicationBase._start_thread`, so this is
  safe).
- Each scheduled callback recomputes the `FairPrice` from the then-current
  cached `BBO`, sets the corresponding field on the stored record to its
  midpoint, and re-sends the **whole** record (not a partial payload) over
  `decorated_order_fill_event` — `SQLiteWriter`'s upsert overwrites every
  column present in the sent row, so resending the full object is what
  keeps previously-filled horizon fields from being clobbered back to
  `NULL`. The 30s callback also drops the record from the in-memory dict.

### 1e. Wiring

`jolteon/app/base.py` — in `ApplicationBase.__init__`, add
`self._post_trade_service =
PostTradeService(fair_price_model=fair_price_model)` alongside
`self._position_manager = PositionManager()`, using the `fair_price_model`
parameter added in 1b. `SignalManager.connect_all()` already auto-discovers
any `SignalSubscriber` attribute (`signal_manager.py:25-28`), so this alone
wires up signal subscription — no change needed to `connect_all()`.
`cli.py` and the per-exchange `Application` subclasses do need the small
passthrough change from 1b so the shared instance actually reaches here.
This also means `decorated_order_fill` gets recorded whenever there are
fills, independent of whether a strategy is attached.

### 1f. Dashboard switch

`jolteon/app/app_pages/orders_pnl.py` — `render()` currently does
`fills = read_table(db_path, "order_fill")` (line 374); switch to
`read_table(db_path, "decorated_order_fill")`. Update the column references
throughout the file to the new field names (`fill_price`→was `price`,
`fill_qty`→was `quantity`, `transaction_timestamp`→was `transaction_time`;
`side`, `symbol`, `fee`, `trade_id` are unchanged) in `fills_table()`,
`pnl_by_symbol()`, and `realized_pnl()`. The existing human-readable-table
pattern (`_readable`, `_optional`, `_notional`) and per-row list rendering
(`render_fills_list`) carry over unchanged — they're column-name-driven, not
schema-specific.

## Part 2: PnL Analysis

Add to `jolteon/app/app_pages/orders_pnl.py` (or a small new helper module
if it grows large), computed directly from the `decorated_order_fill` frame
— no new service or persisted state needed, since every input is already a
column on that table:

```
spread_capture = fair_price_at_fill - fill_price   (BUY)
                  fill_price - fair_price_at_fill   (SELL)

markout_pnl(h) = fair_price_h - fill_price          (BUY)
                  fill_price - fair_price_h          (SELL)
                  for h in {100ms, 1s, 5s, 30s}, skipped while that
                  horizon's column is still NULL (fill too recent)

per-fill PnL   = spread_capture + markout_pnl(30s) - fee
                  (InventoryPnL intentionally omitted for now — add it
                  later)
```

Present as a new section on the same page: per-fill spread capture already
fits the existing `fills_table()`/`render_fills_list()` as an extra column;
average markout per horizon (if our average 1s/5s markout is strongly
negative, we're being systematically picked off) is a better fit as a
small metrics row using the existing `animated_metric()` helper, following
the same pattern as `_render_pnl()`. This is additive — it does not
replace the existing cash-flow-based `pnl_by_symbol()`/`realized_pnl()`
metrics, which keep working once their column references are updated per
1f above.

## Verification

- Unit tests, following existing conventions
  (`unittest.IsolatedAsyncioTestCase`, connecting real signals rather than
  mocking the bus — see `tests/strategy/market_making/
  test_market_making_strategy.py` and
  `tests/execution/coinbase/test_coinbase_mock_execution_service.py` for the
  pattern):
  - `IFairPriceModel.calculate()` sends `fair_price` with the right
    `symbol`/`bid_fair_price`/`ask_fair_price` for a given `BBO`, and
    returns the same `FairPrice` it emits (`test_mid_price_model.py`).
  - `MarketMakingStrategy` still quotes symmetric bid/ask around mid-price
    with the updated `FairPrice`-returning model (existing test, updated
    for the new return type — behavior unchanged since bid == ask today).
  - `MarketMakingStrategy` and `PostTradeService`, constructed with the
    same shared `IFairPriceModel` instance, derive matching fair prices
    for the same `BBO` — guards against the two drifting apart if the
    shared-instance wiring (1b) ever regresses to two separate instances.
  - `PositionManager` emits a correct `PositionUpdate` (resulting volume)
    on a fill.
  - `PostTradeService` derives the right `inventory_before`/`inventory_after`
    across a sequence of fills (including the first fill for a symbol,
    where `inventory_before` should be `0.0`); emits an initial
    `DecoratedOrderFill` with `fair_price_at_fill` set to the midpoint of
    `FairPrice` and the horizon fields `None`; emits updated records at
    each horizon with the right field filled in and earlier fields
    preserved; skips decorating a fill with no `BBO` seen yet.
  - Dashboard helpers (`fills_table`, `pnl_by_symbol`, `realized_pnl`,
    and the new spread-capture/markout functions) against a small
    hand-built `decorated_order_fill` DataFrame.
- End-to-end: run `--paper` mode (`jolteon/cli.py`) briefly against Kraken
  or Coinbase, confirm `decorated_order_fill` rows appear in the SQLite DB
  with horizon fields populating over the following 30 seconds, and that
  the dashboard's Orders & PnL page renders the new data (spread capture
  and markout metrics) without errors, before and after a fill.

## Commits

Land this as separate, reviewable commits:
1. `IFairPriceModel` — `FairPrice(bid, ask)` return type + template-method
   refactor + `fair_price` signal + `MarketMakingStrategy` quoting update +
   tests.
2. `PositionManager` — add `position_updated` signal + test.
3. `PostTradeService` + `DecoratedOrderFill` (new module, taking a shared
   `fair_price_model`) + test.
4. Wire `PostTradeService` into `ApplicationBase`, threading
   `fair_price_model` through `KrakenApplication`/`CoinbaseApplication`/
   `cli.py` so it shares one instance with the strategy.
5. Dashboard — switch to `decorated_order_fill`, add spread capture /
   markout PnL sections.

## Part 3 (follow-up, not detailed here): Better fair price model

```
Fair = Mid + αSignal
```

where Signal initially consists of:

* Order-flow imbalance
* Short-term price momentum
* Cross-venue BTC price
* Possibly perp basis/funding

Then quote:

```
Bid = Fair - Spread/2
Ask = Fair + Spread/2
```

The key is that our fair value should move before the market moves. We
could add the above 4 one by one. Some of the signal will require a better
market data feed, or a weighted market data feed combining several
exchanges.

Needs its own scoping session because of data-infra gaps found during
exploration:

- **Momentum** is the cheapest to start with — derivable from the existing
  `market_trade`/`ticker` feeds, no new market data plumbing required.
- **Order-flow imbalance** needs L2 order book depth; Kraken's
  `public_feed.py` currently only subscribes to `trade` and `ticker`
  channels (no book channel), and the existing `OrderBook`/`SidedOrderBook`
  classes are only used inside a mock execution service today, not
  populated by any live feed.
- **Cross-venue BTC price** needs a second live feed running concurrently
  and combined — no multi-exchange aggregation exists yet (Kraken and
  Coinbase feeds are each independent, single-symbol).
- **Perp basis/funding** has no existing data source of any kind in this
  codebase.
- With `FairPrice(bid, ask)` now in place (1a), asymmetric signals (e.g.
  inventory skew) have a natural home — `_calculate()` can simply return
  different `bid`/`ask` values instead of needing an interface change.

Recommend scoping Part 3 as its own plan once Parts 1-2 land, likely
starting with momentum.
