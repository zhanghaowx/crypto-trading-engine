# Dashboard

Jolteon ships a [Streamlit](https://streamlit.io/) dashboard with two pages: **Live**, for watching
a run's health, market data, risk limits, and orders/PnL, and **Parameters**, for retuning the
engine while it runs.

The Live page is a read-only viewer: it never talks to the running engine directly, and instead
polls the SQLite database that `SignalRecorder` already writes every recorded signal into (in WAL
mode, so the reads never block the engine's own writes). This means it runs as a completely separate
process from the engine and can be pointed at either a live run's database or a replay's.

## Running it

```bash
uv run poe dashboard                                   # reads /tmp/jolteon.sqlite by default
streamlit run jolteon/app/dashboard.py -- --db /tmp/replay.sqlite   # point at a specific database
```

`--params-db` points at the database the Parameters page pushes into, matching the engine's own
flag of the same name. It defaults to `/tmp/jolteon.params.sqlite` on both sides.

## Live page

* **Health** — heartbeat status for each monitored component, shown first since a stale component
  makes everything below it stale too.
* **Market Data** — recent mid price and BBO for the traded symbol.
* **Risk Limits** — current state of the configured risk limits (order frequency, inventory, ...).
* **Orders & PnL** — recorded orders, fills, and running PnL.

## Parameters page

Two tabs. **Engine** edits every tunable the engine reads; it is generated from what each parameter
group declares, so a tunable added to the engine appears here on its own. Edits are staged locally
and reach the engine only when committed, and each field reports what the engine did with it —
applied, not read yet, not picked up, or rejected with a reason. The staged changes and the
Commit/Revert buttons sit at the bottom of the tab, under the parameter cards.

**Dashboard** holds the settings for this viewer alone: auto-refresh and the chart window. The
database paths are not editable there — they come from the launch flags above, so the page can
never read a different file than the one it reports.

This is the one part of the dashboard that writes, and it writes to a database of its own that the
engine polls, so neither process ever writes the file the other owns. See
[the parameters design note](../design/parameters.md) for how that loop works.
