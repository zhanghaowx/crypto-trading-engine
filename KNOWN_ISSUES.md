# Known issues

Problems that have been diagnosed but not yet fixed, with enough context to
pick each one up cold. Recorded 2026-09-09.

Ordered roughly by how much they matter. Each entry says what is wrong, how
it shows up, and where the code is.

---

## 1. Engine structure

- **A `Heartbeater` can only be constructed inside a running event loop.**
  `jolteon/core/health_monitor/heartbeat.py:94` calls `asyncio.create_task`
  from `__init__`. Constructing an application outside a loop raises
  `RuntimeError: no running event loop`, and the failed construction then
  makes `__del__` raise `AttributeError: '_heartbeating_task'` because the
  attribute was never assigned. This makes the engine awkward to script or
  test outside `asyncio.run`.
- **Heartbeat tasks land on whichever loop constructed them.** This is
  implicit and easy to get wrong. It is the reason blocking work on the main
  loop used to delay heartbeats and make healthy components look down.
- **Shutdown lags by up to ten seconds.** `ApplicationBase.THREAD_SYNC_INTERVAL`
  is 10, and the main loop polls the market data thread at that interval. A
  5,000-trade replay that finishes almost instantly still takes 10.02s.

---

## 2. Smaller things, knowingly accepted

These were deliberate trade-offs rather than oversights. They are recorded
so the reasoning is not lost, not because they need action.

- `IDataSource.TRADE_CACHE` is a class-level dict with no eviction, so every
  downloaded range stays resident for the life of the process.
- `SQLiteWriter` drops a batch that SQLite rejects rather than retrying it,
  because retrying a rejected batch would stall every row queued behind it.
  Its queue is also unbounded, so a stalled disk grows memory rather than
  applying backpressure.
- `HistoricalFeed` still re-filters trades in Python after the data source
  has already filtered them in SQL. This is harmless and intentional: other
  data sources return a superset of the requested range.

---
