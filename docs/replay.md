# Recorded-market replay

Replay Binance.US BTC/USD using the same market-making composition as paper
trading and the current mock execution model. This checks reproducibility, not
whether simulated fills are realistic or the strategy is profitable.

## Run the saved example

From the replay worktree:

```bash
uv run jolteon-replay validate --manifest data/recordings/binance-us/BTC-USD/replay-example.json
uv run jolteon-replay run --manifest data/recordings/binance-us/BTC-USD/replay-example.json --speed 1x --output /tmp/replay-one
uv run jolteon-replay run --manifest data/recordings/binance-us/BTC-USD/replay-example.json --speed 10x --output /tmp/replay-ten
uv run jolteon-replay compare /tmp/replay-one /tmp/replay-ten
```

Also supported: `24x` and `unbounded`. Each run must use a new output directory.
Source SQLite files are opened read-only in a consistent transaction. They are
never indexed or changed. The caller supplies the same input recording; no copy
or preparation command is required. The large saved dataset is excluded from Git.

The ten-second example begins on 2026-09-24 at 06:19:45 UTC and includes a fill.
Preceding data initializes the book and indicators without permitting trading;
that warm-up does not wait for real historical time to pass. At 1x the evaluated
interval takes at least ten seconds, plus input loading, warm-up, and output work.
Falling behind increases reported pacing lag; no events are skipped.

## Manifest

The checked-in example is a complete manifest, using recorded startup parameters
explicitly adapted to the current schema. Every default parameter group and every
supplied symbol scope must be complete. Unknown fields, missing groups and out-of-
range values are errors. Secrets do not belong in manifests. This entrypoint only
constructs simulated execution and cannot submit real orders.

`configuration.mode` is either `fixed` with explicit `parameters`, or `recorded`
with startup parameters and complete accepted revision history read from the
selected run. Old recordings lacking revision history require a fixed experiment.
Instrument rules may be supplied in `initialization.instrument_override` with a
reason when historical rules cannot be established. That assumption qualifies the
verification result; it does not prove reproduction of the original paper run.

The interval is `[start,end)`. Choose exactly one source run. Book snapshots before
start initialize the book; if the run begins before its first snapshot, quotes
wait until the book arrives. Engine inventory and trading cash start at zero; this
is the existing unconstrained paper simulator, not a funded spot-account model.

## Results

Each output directory contains:

- `recording.sqlite`: the normal engine recording with a new EngineRun identity.
- `events.jsonl`: semantic outputs, with incidental IDs normalized while preserving
  order/cancel/fill relationships.
- `result.json`: original manifest, effective input hash/counts, code identity,
  completeness limitations, real UTC start/end, status and terminal state.
- Engine log files.

Comparison checks input identity/configuration before comparing output event
order, prices, quantities, timestamps and relationships, then final positions,
working orders and cash/marked PnL. It reports the first divergence and neighboring
outputs. Existing analysis computes fees, notional, realized PnL and markouts with
coverage; missing future observations are not treated as zero markout.

Exit statuses for `compare`: `0` means equivalent without documented limitations;
`2` means equivalent with limitations (not a strict completeness pass); `1` means
input/result mismatch or invalid/incomplete results. Reports are JSON and can be
redirected to a file. Failed/interrupted runs cannot pass comparison. A process
killed before terminal metadata is written remains `running` and is incomplete.

## Validation

Unit tests use virtual pacing and tiny synthetic market events. Normal CI never
runs the long real recording at 1x. The private recording is an opt-in acceptance
input: run the short example in four fresh processes and compare all outputs.
The nearly 24-hour interval in the milestone plan is reserved for extended tests.


## Recording format change

New recording writers append instrument rules instead of replacing a symbol's
previous row, and store external-event sequence numbers. Start live recording in
an empty recording directory when adopting this version; existing symbol-keyed
instrument tables are not migrated. The replay reader still accepts the saved
legacy recording with explicit limitations.

Difference reports include the current BBO, top three book levels, active parameter
revision and nearby output events. Accepted parameter revisions are also persisted
on the simulated timeline in replay output recordings.
