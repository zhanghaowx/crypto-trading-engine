# Replay input audit

Initial audit for the reproducible replay milestone. No engine behavior changed.

## Terminology

Use **replay input** for the source recording and interval (`ReplayInput`), and
**run configuration** for recorded parameters and environment. The dataset JSON
is replay input metadata, not yet an executable experiment manifest.

## Findings to resolve in PR 1

- `DatabaseDataSource` attempts to create a source index. The new workflow must
  open immutable source recordings read-only and never modify them.
- Trade queries filter by time but not symbol or run. Explicit run and symbol
  selection is required for the archived multi-run database.
- Existing SQL bounds use inclusive BETWEEN. The manifest must define and apply
  a consistent half-open interval to avoid boundary duplication.
- Automatic bounds come from trades and can omit the initial book snapshot.
  Initialization must include the snapshot and any required preceding updates.
- Current replay uses exchange time, sorting books before trades at equal times.
  This is a replay convention, not proof of the original cross-stream order.
- `ReplayInput` currently carries a path, optional run ID, and trade count.
  Add immutable content identity and validate it against the archived metadata.
- The CLI composes the adjusted market-making strategy for paper mode separately
  from replay. Manifest execution must explicitly construct the intended strategy
  and load captured configuration rather than assuming the paths are equivalent.
- `TimeManager` is process-global and freezes timestamps without scheduling domain
  timers. Scheduler and pacing work remains PR 2/3.

The selected source and its limitations are documented in reproducible-replay.md.
