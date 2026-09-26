# Replay milestone verification

Implementation is available on `codex/reproducible-replay` in the dedicated
`crypto-trading-engine-replay` worktree. No frontend changes are included.

## Required checks

- `uv run poe architecture`: 3 passed.
- `uv run poe test`: 1,128 passed, 231 subtests passed.
- Line coverage: 6,494 / 6,494 statements (100%).
- `git diff --check`: passed.
- New-format synthetic inputs pass strict comparison in four fresh processes at
  1x, 10x, 24x and unbounded speed.

## Saved real-data verification

Four fresh processes replayed 2026-09-24 06:19:45–06:19:55 UTC from source run
`20260924T034440Z-e43bf76d`, including preceding initialization data. All completed.
The archived SQLite checksum was verified before running.

Each speed produced 94 fair prices, 47 fair-price adjustments, 47 quote offsets,
72 orders, 70 cancellations, one fill and one position update. Semantic event
streams, terminal state and derived economics matched across all four speeds.
Comparison returned `equivalent-with-documented-limitations` (exit code 2):

- Instrument rules were supplied explicitly; historical rules are unverified.
- Legacy event order cannot establish the original live delivery order.

The recorded source was not changed. This establishes reproducibility for the
specified experiment, not profitability or reproduction of the original live run.
The approximately 24-hour interval at 1x remains optional extended validation and
was not run.

Local artifacts (ignored by Git):
`data/replay-results/verification-20260926T012528Z/`, including `verification.json`,
`comparison.json`, and each speed's recording, events and result metadata.

Source SHA-256: `69c15f2305334905691450fcf43b9927d75dfe0b670e570e5429babe63144846`.

Consumed input SHA-256: `aa9c9573697065f34e7d829a45f9ccf5a40944608607f167255462acf0ee2357`.

Runtime source SHA-256: `0081aabeb38dc65ec7a3242633198a00236dcc0a7a62fc1b6ad0b0e79cdeac29`.

## Issue outcomes

#117's simulated clock and pacing work is implemented and validated; it is ready
for review toward closure. #122's replay milestone is implemented with the saved
legacy input limitations reported explicitly. #102 remains open for profitability
evidence, #70 for remaining global services, and #68 for execution latency models.
No GitHub issue has been closed or modified.

New recording writers require an empty recording directory to retain append-only
instrument history; existing symbol-keyed instrument tables are not migrated.
