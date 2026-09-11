# L2 Order Book Feed

A plan for giving the engine real order book depth, normalized so that any
exchange adapter can populate it and any consumer can read it without
knowing which exchange produced it.

## Why

The engine sees only the top of book today, via the exchange's ticker
channel, normalized into `BBO`. Every depth-aware signal is therefore
unbuildable: order-flow imbalance, depth-weighted fair price, and
queue-aware quoting all need levels behind the touch.
`MicropriceAdjustment` approximates imbalance from the two resting
quantities in the `BBO` alone, which is the best proxy available without
depth but discards the rest of the book.

The goal is not "subscribe to Kraken's book channel". It is a normalized
book that a second and third exchange can fill in later without reworking
the consumers.

## What exists today

- `jolteon/engine/market_data/core/order_book.py` holds an `OrderBook`
  that only accumulates. `add_bid(price, quantity)` does
  `levels[price] += quantity`. There is no removal, no replacement, no
  ordering, and no best-bid accessor. Nothing calls it at all since the
  Coinbase integration was removed, so there is no contract to preserve
  and the rewrite below is free.
- `Events` declares three signals: channel heartbeat, ticker, and market
  trade. There is no book signal.
- Kraken's `PublicFeed` subscribes to `trade` and `ticker`. It implements
  no shared interface, and `ApplicationBase._md` is typed `object`.
- `FairPriceContext` carries a single `bbo` field.
- `HistoricalFeed` replays market trades only, so replay has no top of
  book at all.

Kraken's `book` channel is public, needs no authentication, and runs on
the endpoint the feed already connects to. It offers depths of 10, 25,
100, 500, and 1000, sends one snapshot followed by incremental updates,
and carries a CRC32 checksum over the top ten levels of each side.

## Design

### Normalized types

`OrderBook` is rewritten around two wire-neutral records.

```python
@dataclass(frozen=True)
class PriceLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class BookUpdate:
    symbol: str
    bids: list[PriceLevel]
    asks: list[PriceLevel]
    is_snapshot: bool
    exchange_time: datetime
```

`BookUpdate` is the form every adapter produces. A quantity of zero means
the level is gone. Kraken sends exactly this shape under different field
names. Translating the wire format into `BookUpdate` is the entire job of
an exchange adapter.

`OrderBook` owns state, ordering, and the reads worth sharing.

```python
class OrderBook:
    def __init__(self, symbol: str): ...

    def apply(self, update: BookUpdate) -> None: ...
    def clear(self) -> None: ...

    def best_bid(self) -> PriceLevel | None: ...
    def best_ask(self) -> PriceLevel | None: ...
    def bbo(self) -> BBO | None: ...
    def bids(self, depth: int) -> list[PriceLevel]: ...
    def asks(self, depth: int) -> list[PriceLevel]: ...
```

`apply` replaces the quantity at a price, removes the level when that
quantity is zero, and clears both sides first when the update is a
snapshot. Both sides are kept as lists sorted ascending by price and
maintained with `bisect.insort`, so the best bid is the last element, the
best ask is the first, and an update costs one binary search plus a list
shift. That beats sorting a dict on every read, which is what the current
class would force.

### Derived features

`OrderBook` holds state, ordering, and neutral reads, and stops there.
Imbalance and depth-weighted price are not reads of the book, they are
interpretations of it: each one picks a depth, a sizing convention, and a
weighting that a strategy is entitled to disagree with. On the book those
choices would be owned by the wrong object, and the book would become the
place every future signal accretes onto.

They live in `jolteon/engine/market_data/core/book_features.py` as pure
functions over the lists `bids` and `asks` already return.

```python
def imbalance(bids: list[PriceLevel], asks: list[PriceLevel]) -> float: ...
def vwap(levels: list[PriceLevel], quantity: float) -> float | None: ...
```

Depth is the caller's choice, expressed in what it passes: a consumer
calls `imbalance(book.bids(10), book.asks(10))`. Free functions over
levels rather than methods on the book also means the derived-feature
recorder and a strategy adjustment share the same arithmetic without
either depending on the other, and a strategy that wants different
arithmetic writes its own without touching the book.

### Feed interface

There is no market data interface today, which is the deeper reason a
second exchange is awkward to wire. Add `jolteon/engine/market_data/feed.py`.

```python
class Channel(StrEnum):
    MARKET_TRADE = "market_trade"
    TICKER = "ticker"
    ORDER_BOOK = "order_book"


class IMarketDataFeed(Heartbeater, ABC):
    def __init__(self, name: str, interval_in_seconds: float):
        super().__init__(name, interval_in_seconds)
        self.events = Events()

    @property
    @abstractmethod
    def channels(self) -> frozenset[Channel]: ...

    @abstractmethod
    async def connect(self, symbol: str, *args) -> None: ...
```

`channels` is what lets a consumer degrade instead of crash.
`HistoricalFeed` reports market trades only. Kraken's live feed reports
all three. A strategy that needs depth can check once at wiring time
rather than discovering an absent book on the first tick.

`connect` stays decorated with `@starts_heartbeating` in each
implementation, so the heartbeat continues to run on the loop that does
the feed's real work. A hang in that loop must still stall its own
heartbeat.

Both public feeds and `HistoricalFeed` become implementations, and
`ApplicationBase.use_market_data_service` takes `IMarketDataFeed` rather
than `object`.

### Who owns the book

Each adapter owns an `OrderBook`, applies its own decoded `BookUpdate` to
it, and publishes the result on a new `order_book` signal. Consumers
receive a finished, queryable book.

The alternative, publishing raw deltas for a central component to
assemble, is rejected. It splits one concept across two places and forces
every consumer to either carry its own copy of the assembly logic or
depend on a coordinator running first. Here the shared logic lives in
`OrderBook` and each adapter holds an instance of it, so nothing outside
the adapter needs to know how the book was built.

The published book is live and mutable. Consumers read it inside their
handler; `bids` and `asks` return fresh lists, so anything a consumer
wants to keep past the handler it copies out.

### Exchange-specific parts

Kraken's checksum is not portable and stays in the Kraken adapter. It is
a CRC32 over the top ten levels of each side rendered as strings at the
instrument's exact decimal precision, which the adapter must first learn
from the `instrument` channel. Converting to float loses the original
rendering, so the adapter has to keep the raw strings or re-render from
that precision. This is why checksum validation is phased second rather
than shipped with the first cut.

Detecting desync is per exchange. Recovering from it is not, so the
recover path belongs on the feed base: clear the book, resubscribe, wait
for a fresh snapshot, and report a heartbeat issue while degraded.

### Recording

Raw book snapshots must not go through `SignalRecorder`. Its serializer
turns a list into numbered keys and the flattener turns those into column
names, so a depth-10 book becomes forty columns from `bids.0.price` to
`asks.9.quantity`, one row per update, at whatever rate the exchange
pushes. The SQLite writer widens a table with `ALTER TABLE` per new
column, and the dashboard reads these tables directly.

Record derived features instead: top of book, imbalance at two or three
depths, and depth-weighted price. That is a small fixed column set, it is
what a signal evaluation page can plot, and it is what a future replay
would need. Full book capture, if it is ever wanted, belongs in a
separate compact writer.

### Consumers

`FairPriceContext` gains an optional book.

```python
@dataclass
class FairPriceContext:
    bbo: BBO
    order_book: OrderBook | None = None
```

`None` is the honest value during replay and on any feed without depth.
Adjustments already abstain by returning 0.0 when they have nothing to
say, so a depth-dependent adjustment abstains when the book is absent. No
existing adjustment changes.

### Two views of the touch

Once the book channel is on, ticker and book both describe the top of
book and they will disagree transiently. Pick one: the book is
authoritative for `BBO` on any feed that provides depth, and ticker fills
in on feeds that do not. Otherwise `BBO` consumers watch the touch
flicker between two views of it.

## Out of scope

- **L2 replay.** It needs recorded book data, which needs the compact
  writer above, and `HistoricalFeed` emits market trades only. Worth its
  own plan once live capture exists.
- **Kraken's level3 channel.** Per-order rather than per-level, and it
  requires an API token.
- **A second exchange.** The interface is shaped so one drops in, but
  Coinbase was never the cheap second venue it looked like: its Exchange
  websocket gates `level2` behind authentication, which is why the
  integration was removed rather than finished. Kraken is the first
  exchange to implement precisely because its depth is public.

## Commits

1. Rewrite `OrderBook` as a real L2 book with snapshot and update
   application, ordering, and BBO accessors. Replace its test; the class
   has no callers to update.
2. Add `book_features` with `imbalance` and `vwap` as pure functions
   over price levels.
3. Add `IMarketDataFeed` and `Channel`. Make the public feed and
   `HistoricalFeed` implement it, and type `ApplicationBase._md` to it.
4. Add the `order_book` signal to `Events`.
5. Subscribe Kraken's public feed to the book channel, decode snapshot
   and update messages into `BookUpdate`, apply, and publish.
6. Add checksum validation and the resync path.
7. Add the derived-feature recorder.
8. Add `order_book` to `FairPriceContext`.
9. Add an order-flow imbalance adjustment that reads the book.

Commits 1 through 4 are a refactor with no behavior change and can land
ahead of the rest.
