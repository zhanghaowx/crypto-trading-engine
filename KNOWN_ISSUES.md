# Known issues

Problems that have been diagnosed but not yet fixed, with enough context to
pick each one up cold. Recorded 2026-09-09.

Ordered roughly by how much they matter. Each entry says what is wrong, how
it shows up, and where the code is.

---

## Smaller things

These were deliberate trade-offs rather than oversights. They are recorded
so the reasoning is not lost, not because they need action.

- `IDataSource.TRADE_CACHE` is a class-level dict with no eviction, so every
  downloaded range stays resident for the life of the process.
