# Dashboard

Jolteon ships a [Streamlit](https://streamlit.io/) dashboard with three pages: **Live**, for
watching one symbol's market data, risk limits, and orders/PnL, **Health**, for watching every
engine at once, and **Parameters**, for retuning the engine while it runs.

The Live page is a read-only viewer: it never talks to the running engine directly, and instead
polls the SQLite database that `SignalRecorder` already writes every recorded signal into (in WAL
mode, so the reads never block the engine's own writes). This means it runs as a completely separate
process from the engine and can be pointed at either a live run's database or a replay's.

## Running it

```bash
uv run poe dashboard                                     # reads /tmp/jolteon by default
streamlit run jolteon/app/dashboard.py -- --root /tmp/jolteon   # point at another root
```

`--root` is the directory every engine writes under, matching the engine's own flag of the
same name. Each symbol traded has a directory there, and those directories are the symbols
the dashboard offers: pick one and every section reads that engine's recording and its logs.

`--params-db` points at the database the Parameters page pushes into. It defaults to
`parameters.sqlite` at the root of `--root`, which one store serves every engine from.

## Live page

Everything here reads the one engine whose symbol is selected above the cards.

* **Market Data** — recent mid price and BBO for the traded symbol.
* **Risk Limits** — current state of the configured risk limits (order frequency, inventory, ...).
* **Orders & PnL** — recorded orders, fills, and running PnL.

## Health page

One engine trades one symbol, so a component's health is only half a fact: the other half is which
engine's it was. This page reads every engine under `--root` rather than the selected one, so an
engine that has gone quiet is visible whichever symbol is on screen.

* **Health** — heartbeat status for each component, grouped by the symbol its engine trades. A
  sender that has not been heard from for 30 seconds reads as DOWN however cheerful its last
  heartbeat was: a process that dies never reports its own death.
* **Errors** — every engine's ERROR and CRITICAL log lines in one list, newest first, each naming
  the symbol whose engine logged it.

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
