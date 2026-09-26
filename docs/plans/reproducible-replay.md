# Reproducible Binance.US replay

## Milestone

Given a fixed recording interval, configuration, initial state, and code version,
produce equivalent strategy decisions, orders, fills, and economics at 1x, 10x,
24x, and unbounded playback speed. This establishes repeatability, not profitable
or realistic execution. No frontend changes are required.

## Terminology

- **Source recording**: the supplied SQLite file; a **recording snapshot** is our
  saved read-only copy, not a required replay preparation feature.
- **Replay input**: the selected external events and initialization inputs from
  one source run and interval.
- **Replay input metadata**: source details, interval, ordering policy, counts,
  completeness, and checksums. Use this instead of recording provenance.
- **Run configuration**: resolved parameters, accepted revisions, and run
  environment. Use this instead of configuration provenance.
- **Replay manifest**: the versioned document specifying replay input selection,
  run configuration, initialization policy, and playback settings.
- **Simulated time**: the domain timeline used by strategy behavior and timers.
- **Playback speed**: pacing relative to real monotonic time; it must not change
  domain results. **Audit timestamps** use real UTC time.
- **Replay result**: recorded outputs and completion state for one replay run.

## Selected source recording

- Source snapshot: `data/recordings/binance-us/BTC-USD/replay-source-20260924T034440Z.sqlite`.
- Replay input metadata and SHA-256: the adjacent `replay-source-20260924T034440Z.json`.
- Selected run: `20260924T034440Z-e43bf76d`, Binance.US BTC/USD, simulated execution
  with realtime market data.
- Acceptance interval: **2026-09-24 03:44:40 UTC inclusive to
  2026-09-25 03:30:00 UTC exclusive**.
- Routine real-data interval: **2026-09-24 06:19:45 UTC inclusive to
  06:19:55 UTC exclusive**, including a fill. Load preceding snapshot/updates
  for warm-up without wall-clock pacing; keep trading disabled until start.
- The earlier three-hour development interval remains usable for extended tests.
- The snapshot contains the entire source database, including older runs. Select
  the named run and interval explicitly; do not replay the whole file by default.
- Store the large SQLite file locally outside Git. Preserve the replay input metadata JSON.
  The snapshot is read-only; replay outputs must go elsewhere.

The acceptance interval contains 3,908 market trades, 355,466 book records, and
47 recorded paper fills; the development interval contains 145 trades, 36,717
book records, and one paper fill. These counts were measured using recorder
timestamps and run identity. The input audit must specify how those bounds map
to exchange timestamps used by replay.

The selected run has 41 startup parameter values and simulation/code metadata.
Its initial book snapshot is at 2026-09-24 03:44:42.130462 UTC, before its first
market trade. Preserve that snapshot: automatic trade-based bounds can omit it.
The acceptance interval ends before the next book snapshot at
2026-09-25 03:34:57.752322 UTC.

Inspection found continuous local book sequences and trade IDs in the selected
run. Reconstruction of the inspected newest-run book found no empty, locked, or
crossed books, no backwards book timestamps, and a maximum update gap of about
15.7 seconds. SQLite quick_check passed. These are input-quality checks, not proof
of exchange-level completeness or profitability.

Limitations:

- The original run reports a dirty checkout; its commit alone cannot recreate
  the original executable source.
- The run was still active when captured. Use the bounded interval; do not infer
  successful run completion from the archived file.
- Instrument metadata is overwritten rather than preserved per run.
- Recorded book sequences are local; raw Binance sequence ranges and a global
  cross-stream event sequence are not retained.

## PR 1: Audit inputs and define the manifest

Audit market trades, book initialization and updates, instruments, ordering,
startup parameters, parameter revisions, starting inventory, and completeness.
Define a versioned replay manifest with immutable source identity, interval, resolved
configuration, initialization/warm-up policy, existing simulator assumptions,
and playback speed. Distinguish replaying recorded parameter revisions from
using a fixed experimental configuration.

Acceptance: required inputs are explicit; missing inputs yield actionable errors
or explicit limitations; current mutable settings never silently replace history.
Document original-paper-run reconstruction limits. Replay-to-replay equivalence
is the required guarantee.

## PR 2: Simulated clock and scheduler

Extend existing time infrastructure with injectable clock and scheduler ownership.
Audit domain clock reads, sleeps, timers, and health behavior affecting trading.
Advance domain time before event delivery and fire timers between market events.
Define deterministic event/timer tie ordering, warm-up, interval end, cancellation,
and failure semantics. Separate simulated domain time, real monotonic pacing, and
real UTC audit timestamps. Operational monitoring must not change trading results
merely because replay runs faster.

Acceptance: deterministic timer tests require no real waiting; cleanup restores
clock state after success, cancellation, or failure; realtime behavior is covered.

## PR 3: Manifest-driven execution and pacing

Construct runs from frozen inputs in fresh processes initially. Support 1x, 10x,
24x, and unbounded pacing. Preserve every event and ordering when processing falls
behind; report lag. Give every replay separate output and record replay manifest, input
identity, code version, effective configuration, and completion state using
existing run metadata.

Acceptance: one CLI command runs without the dashboard or mutable parameter
database; sources and previous outputs remain intact; speed changes wall-clock
duration only; incomplete runs are identifiable.

## PR 4: Compare and verify

Compare consumed inputs, fair prices and quote decisions, orders, cancellations,
fills, final positions, and existing economics. Normalize incidental IDs and audit
timestamps while preserving relationships. Specify numeric tolerances and report
the first meaningful divergence with surrounding events.

Acceptance: a small checked-in synthetic fixture passes at every speed; the
bounded real recording passes repeated fresh-process checks; injected differences
are detected; incomplete outputs cannot pass. Use controlled clocks for automated
pacing checks rather than waiting through a full real-time dataset.

## Issue outcomes

| Issue | Outcome |
| --- | --- |
| [#117](https://github.com/zhanghaowx/crypto-trading-engine/issues/117) simulated clock and pacing | Close after all clock, scheduling, pacing, audit-time, and cleanup criteria pass. |
| [#102](https://github.com/zhanghaowx/crypto-trading-engine/issues/102) profitability gate | Complete reproducible-replay work and reconcile existing metadata progress; keep open for validation reports, sensitivity, and profitability evidence. |
| [#70](https://github.com/zhanghaowx/crypto-trading-engine/issues/70) service ownership | Advance clock/scheduler injection; keep open for remaining global services. |
| [#68](https://github.com/zhanghaowx/crypto-trading-engine/issues/68) execution latency | Supply scheduling foundation; keep open for delayed order/cancel behavior. |

[#122](https://github.com/zhanghaowx/crypto-trading-engine/issues/122) is the
more detailed implementation specification for this milestone. This local plan
also preserves the selected dataset and its audit findings. Before adopting its
strict validation contract, resolve these dataset compatibility questions:

- The selected interval begins before its first book snapshot. Either support an
  explicit startup phase with trading disabled until initialization completes,
  or move the evaluation start after a valid snapshot. Do not silently change it.
- The saved instrument row may postdate the selected interval and has no source
  run attribution. Audit whether an unambiguous historical specification exists;
  reject strict verification if it cannot be established.
- Keep the full-file SHA-256 as archive integrity metadata. Consumed-event hashes
  from #122 verify replay input equivalence; no copy/preparation command is needed.
- Use a small real-data interval for four-speed integration checks. The long
  interval is a separate extended test, since 1x takes almost 24 hours.

No issue is closed merely by writing this plan. Session-scoped events (#65),
authoritative order state (#66), queue scenarios (#103), and Replay frontend
(#108) remain separate. No parameter search, new strategy policy, or profitability
claim is included.

## Placement and validation

Time infrastructure belongs in engine/core/time; replay delivery in
engine/market_data; composition in engine/runtime; thin commands in cli; economic
calculations in analysis. Preserve dependency rules and extend existing packages.
Each implementation PR adds appropriate coverage and passes:

```text
uv run poe architecture
uv run poe test
```


## Implementation decisions

- CLI: `jolteon-replay validate`, `run`, and `compare` (also available as
  `python -m jolteon.cli.replay`). No recording preparation command.
- Legacy inputs use recorder timestamps, channel priority, and row IDs. New
  recordings retain a global external-event sequence and append instrument
  history. Breaking changes are allowed; no general schema migration framework.
- Initialization is `flat-await-inputs`: zero strategy inventory/trading cash,
  no orders, and no quoting until instrument and book initialization is complete.
  Warm-up starts at the preceding book snapshot and is not paced in real time.
- The example explicitly supplies instrument rules with an uncertainty reason.
  Its recorded parameters were adapted by removing the obsolete Kraken-only
  `dry_run` field; unknown fields are rejected, never silently discarded.
- Operational heartbeats remain on real time and are not replay trading gates.
  Domain deadlines and parameter revisions use the simulated scheduler. Timers at
  an event time run first; timers created during delivery run after its cascade.
  External events exclude the end timestamp; domain timers include it.
- Future input order and historical rule assumptions are reported separately.
  Legacy qualified equivalence is not a strict completeness pass.
- Runtime sources are hashed in addition to the Git commit so dirty checkouts
  cannot masquerade as the same executable code.

## Implementation status

Implemented in the dedicated worktree. See [verification results](replay-verification.md)
for required checks, the saved four-speed run, recording limitations and issue
outcomes. The long 1x run remains extended validation.
