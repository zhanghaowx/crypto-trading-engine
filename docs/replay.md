# Recorded-market replay

Replay Binance.US BTC/USD using the same market-making composition as paper
trading and the current mock execution model. This checks reproducibility, not
whether simulated fills are realistic or the strategy is profitable.

## Run the saved example

From the repository root, with the private recording placed beside the
manifest under `data/recordings/binance-us/BTC-USD/`:

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

## Timeline

Simulated time is the recorder's timestamp on each external event. A recording
that carries an external-event sequence is replayed in that order. An older
recording is ordered by recorder time, then channel, then row, which cannot
establish the original live delivery order and is reported as a limitation.
Domain timers due at an event's time fire before the event; a timer created
while an event is delivered runs after that event's signal cascade. External
events stop before `end`; timers due exactly at `end` still fire. Playback
speed only paces delivery against the machine's monotonic clock. Operational
heartbeats stay on real time and never gate replay trading, so host load
cannot change a decision between speeds.

## Results

Each output directory contains:

- `recording.sqlite`: the normal engine recording with a new EngineRun identity.
- `events.jsonl`: semantic outputs, with incidental IDs normalized while preserving
  order/cancel/fill relationships.
- `result.json`: original manifest, effective input hash/counts, code identity
  as the commit plus a hash of every runtime source file so a dirty checkout
  cannot pass for the same code, completeness limitations, real UTC start/end,
  status and terminal state.
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

That recording is a snapshot of `/tmp/jolteon/binance-us/BTC-USD/live.sqlite`
taken on 2026-09-25, SHA-256
`69c15f2305334905691450fcf43b9927d75dfe0b670e570e5429babe63144846`, holding
source run `20260924T034440Z-e43bf76d` among older runs. Its full interval,
2026-09-24 03:44:40 to 2026-09-25 03:30:00 UTC, is reserved for extended tests:
at 1x it takes almost a day. The run was still active when captured, its
checkout was dirty, and it predates instrument history and the external-event
sequence, so a comparison on it reports those limitations and exits with `2`.

## Recording format change

Recording writers now append instrument rules instead of replacing a symbol's
previous row, and stamp every external event with a sequence number. A
recording an older writer created keeps its symbol-keyed instrument table and
is not migrated, so do not point a new writer at one. The replay reader still
accepts such a recording, with the limitations described above.

Difference reports include the current BBO, top three book levels, active parameter
revision and nearby output events. Accepted parameter revisions are also persisted
on the simulated timeline in replay output recordings.
