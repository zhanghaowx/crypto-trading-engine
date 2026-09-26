# Jolteon design prototype

A dependency-free, interactive design proposal for the dashboard, and the
place where the dashboard's design choices are made. The rules those
choices have to keep are in [UI_GUIDELINES.md](../../UI_GUIDELINES.md);
this README says what the current direction is and why.

Open `index.html` in a browser, or from the repository root run:

```sh
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 \
  --directory jolteon/dashboard/static/prototype
```

Visit http://localhost:8765. All data is illustrative and parameter changes
affect only in-memory demo state. Reloading resets the demo. The existing
dashboard on port 8501 is unchanged.

`styles.css` owns the tokens and reusable layout styles; `app.js` owns
fixtures, shared rendering, and interactions; `index.html` owns the
document shell. No external fonts or packages load. `styles.css` is the
executable reference for every colour and measure: `.streamlit/config.toml`
paints Streamlit's widgets from its values and `static/tokens.css` repeats
them for the dashboard's own stylesheets, held to it by
`tests/dashboard/static/test_tokens.py`.

This is a design artifact, not a replacement Streamlit application. Its
sample fields, charts and status history do not introduce production data
requirements. Do not connect its demo parameter actions to an engine or use
its fixture values as trading defaults. The wordmark is a proposed
treatment; existing brand assets remain available.

## What to try

The workspace switch; the monitor layout switch in the Trading navigation
(Dashboard or Cockpit, below); the engine selection, where ETH/USD is an
engine that has stopped and shows how the monitor, Health and Parameters
say so; the Live/Paused control on the monitor; the order book's `ours` tag; the fills'
side filter, markout horizon switch and identifier toggle; the Health
preview states across both engines, including the populated error log; the
parameter scope switch and the state badge on every field (default,
inherited, override, pending, stored and awaiting the engine); parameter
edit/review/apply/revert with each change's scope named in the review; the
Runs source filter; opening a run from the table; a replay's capture link
back to the run that recorded its data; and Compare with two runs over one
window and then over two.

The palette switcher in the header (Slate / Sage / Morandi / Slate dark)
swaps the same token set between complete neutral-and-accent combinations,
so the layout and content are held constant while only the palette
changes. It is a comparison aid, not a decision: Slate is the direction,
and the palette `.streamlit/config.toml` carries. Only the neutrals and
the brand accent move between the three light palettes; Positive,
Negative, Warning and Information keep their hues, muted for Morandi to
match its lower-saturation character. Slate dark inverts Slate for a
screen watched for hours beside other terminals: the same roles, so every
rule about them holds, with the surfaces drawn in ink (the primary button,
the toast, the guide's opening) inverting with it. The chosen palette is
remembered in this browser only.

## The current direction

Everything in this section is a choice. It can be revisited, and a
redesign starts by changing it here.

### Two workspaces

The dashboard is split at the top level by where a run's market data came
from, because that is what decides how a screen behaves:

| | Trading | Research |
| --- | --- | --- |
| Subject | one engine reading a live feed, now | runs that have finished |
| Refresh | refreshes, and says when it last did | never; the numbers are final |
| Parameters | editable, and reach the running engine | a frozen input, shown read-only |
| Health | reported per component | absent; a finished run has no heartbeat |
| Time | one clock, moving | a data window, and the wall clock a run spent |

Trading holds Health, Live monitor and Parameters. Research holds Runs and
Compare, with run detail reached by choosing a run rather than by
navigating to it. Health leads the Trading order because it says whether
the numbers can be trusted, but the workspace opens on the monitor.

Execution mode - paper or real - is not a workspace. It rides along as a
badge, because it changes what is at stake rather than how a page works.
A finished live session belongs to Research alongside replays: the same
analysis applies to both, and the run states which it was. Research is
named for what it lists; calling it Replay would hide a finished live
session inside it.

Two engines are configured and only BTC/USD is running. ETH/USD stopped
two days ago, and choosing it shows how a stopped engine is met: the
monitor drains its pulse, says when it stopped and points at the finished
run; Health lists its components as stopped with it rather than down;
Parameters says an edit waits for it to start.

### Page anatomy

1. Persistent navigation within the current workspace. It names the page;
   no page repeats its name as a heading of its own, so the room under
   the header goes to the page's content. Only the style guide, a document
   rather than a screen, keeps a heading.
2. A context bar identifying the scope, mode, run, and either freshness, a
   stop time or the data window.
3. Up to four summary metrics when they help the task. Each has a name, a
   value, a unit or scope, and an optional explanatory line.
4. Primary content in aligned columns, then supporting tables and details.

### Type, spacing and shape

One sans-serif family throughout, with system fallbacks; hierarchy comes
from weight, not from a second family.

| Role | Treatment |
| --- | --- |
| Document heading | 29 / 600, style guide only |
| Card heading | 15 / 600, the same on every card |
| Body and controls | 14 / 400 to 500 |
| Context and supporting text | 12 / 400 |
| Compact table headers and metadata | 10 to 11, secondary content only |
| Summary value | 28, tabular figures |

One spacing scale (4, 8, 12, 16, 24, 32) with no values between its
steps. Card insets and section gaps share a value. Desktop page gutters are
wider than mobile ones. Content has a maximum width, and a table never
stretches the page past it. Cards have one radius (10px), controls another
(6px), badges a third (4px). Borders separate surfaces; there are no
decorative shadows.

### Components

Cards share a header inset, heading style and action area on the right;
controls are never positioned over a long title. Essential context stays
visible when details are collapsed, and a hidden card stays restorable.

A live feed rests behind a pulse and a last-updated time, paired with the
control that stops it. Paused keeps the indicator in place and drains its
colour. A stopped engine keeps the same spot, drained, with when it
stopped, and a neutral notice above the metrics links to the finished
run.

Summary metrics are four tiles. On the monitor they are marked PnL with
cash flow and inventory as its note, the position with its value at mid
and its share of the limit, fills by side, and fees. A sparkline appears
only on a metric with measured history.

The order book is two side-by-side tables with depth shading from the
actual cumulative size, the mid price and spread between them, and a
small `ours` tag on any level holding one of our quotes. Risk limits and
fair-price signals stack beside it. Each signal carries a verdict badge -
Weighted, Too weak to size from, Warming up - and its contribution, or
`–` when it has none.

Fills show one markout column, switched by horizon, with identifiers
behind a toggle and the symbol left to the context bar. A horizon that
has not passed yet is `–`.

Tables use a quiet header band, horizontal row separators and no vertical
gridlines. Signed figures are coloured; cells are not filled.

Health groups its component tiles under an engine row, with plain names
(Market making, Paper execution, Public feed, Parameters) rather than
class names. A stopped engine's tiles say they stopped with it. The
navigation dot on Health appears only while a component is down.

Parameters lists selected groups from the production catalog under the
part of the engine each one configures - Strategy, Venues, Runtime - in
sentence case. Each field has a persistent label, a state badge, a unit
beside the input and a one-line explanation. The scope switch chooses
between the defaults for all symbols and one symbol's overrides. The save
bar counts pending changes and the review names each change's scope.

A run in Research states its execution mode and market-data mode as two
badges; a replay adds a chip linking to the run that captured its data.
The parameters a finished run used are a read-only table with the
current live value beside each, marked Frozen. Compare shows only the
parameters that differ, and how many of how many.

## The cockpit, for comparison

The Trading navigation carries a second monitor layout, Cockpit, beside
the Dashboard layout above. It is the other answer to what a monitor is
for: the same sample data on one screen, shaped around what a market
maker watches, and a comparison aid rather than a decision. The choice is
remembered in this browser only.

- **A status strip** across the top: the engine and its run, the feed's
  pulse with the Live/Paused control, the position against its limit,
  marked PnL, our two quotes with the fair price beside them, and how
  many components are reporting. Parameters carries the same strip in
  this layout; Health does not, because Health reads every engine and
  the strip is one engine's.
- **A price ladder** in the middle: one column of prices with the
  market's bids and asks on either side, depth shading from cumulative
  size, our resting quotes tagged `ours` at their level, and the adjusted
  fair price drawn as a dashed line through the ladder, so where we quote
  and where we think the price is are read together.
- **The PnL line with every fill on it**, buys under the line and sells
  above it, and a dense fills tape beneath with a link back to the full
  fills table in the Dashboard layout.
- **A position panel** on the left with the limit bar, the PnL broken
  into cash flow, inventory and fees, each signal's verdict and
  contribution, and every component's state.
- Denser type and insets than the card layout. The same tokens, the same
  rules: a stopped engine drains the strip and marks the ladder as its
  last snapshot; a warming signal is a neutral badge; only the signed
  figure is coloured.

In production this is a decision about the shell, not a styling pass: a
ladder, a chart with markers and a persistent strip fight Streamlit's
page model, and the prototype is already a working front-end that would
need only a read-only source for the recordings.

## Why it looks this way

Two reviews of the production dashboard at `http://localhost:8501`, with
the direction each finding led to.

### Before the migration

Live, Health, and Parameters were inspected in rendered screenshots. The
Post-trade browser capture was still loading its session card; the review
of its completed content is based on the source.

| Behaviour then | Effect | Direction |
| --- | --- | --- |
| Live starts with run metadata; Health starts directly with cards; Parameters starts with tabs | Page hierarchy changes during navigation | A shared anatomy: navigation, context bar, metrics, then content |
| Live places a tall order book beside a short risk card | Large unused space and session results below the fold | Summary metrics first; compact bid/ask columns beside risk and signals |
| Parameters displays many groups in three masonry columns | All settings compete for attention; commit controls sit after a long form | Group navigation, aligned field rows, visible change summary |
| Healthy cards have a strong green edge; no-error/no-fill states use blue alert panels | Normal operation receives too much visual emphasis | Neutral surfaces and compact status badges; quiet empty states |
| Card CSS names Space Grotesk, the theme defines three font families, and multiple CSS files repeat colors | Changes can drift across cards and pages | One UI family, one number style, shared semantic tokens |
| Several card titles use title case, while parameter labels use sentence case | Inconsistent voice | Sentence case everywhere, preserving proper names and acronyms |
| Run metadata uses UTC while health reports use local time | Readers must translate timestamps across pages | Explicit, consistent timezone within a view; UTC by default |

Kept from the existing dashboard: shared Card rendering, centralized
number formatting, per-card refresh, visible risk thresholds, run-scoped
analysis, missing-value markers, and staged parameter changes.

### After the migration, 2026-09-25

Reviewed while the dashboard's one engine had been stopped for a day.
ETH/USD in the prototype is that engine.

| Behaviour then | Effect | Direction |
| --- | --- | --- |
| Live shows a stopped engine with a Live feed badge, a green pulse and "Refreshing every 5 s"; Health lists its four components as down; Parameters says an edit reaches the running engine | Three pages say something is running when nothing is, and the navigation wears an alert for an engine that was switched off | Stopped is its own quiet state: the pulse drained beside when it stopped, a Stopped badge, a neutral notice linking to the finished run in Research, tiles that stopped with the engine, and no alert dot |
| Live's summary is six bare numbers - Total PnL 2.54, Net cash flow 271.23, Inventory value -268.69 - and Post-trade calls the same 2.54 Marked PnL | No currency, no sign, the parts of a total beside it as peers, and two names for one figure | Four metrics with units and signs; cash flow and inventory as the note under marked PnL; the position as a metric of its own; one name on every page |
| Risk limits stands alone beside a tall order book | A quarter of the screen is empty | Risk and fair-price signals stack in the right column |
| Fair price signals renders "No usable signal yet" as a red table row | A signal still warming up looks like a failure | A neutral verdict badge beside each signal's contribution, and "–" where there is none yet |
| Recent fills has fourteen columns: two identifiers, the symbol, and four markout horizons | Too wide to scan, and the symbol repeats the context bar | One markout column with a horizon switch; identifiers behind a toggle; the symbol only in the context bar |
| Trade quality and Execution economics fill every cell red or green | A table of ordinary results reads as a heat map of alarms | Colour on the signed figure only |
| Health nests its tiles inside a card, names them after classes (MockExecutionService), and reports local time | Double framing, code names, and a second clock | Tiles grouped under an engine row, plain names, UTC |
| Parameters lists nineteen groups at equal weight in title case, with the unit in the label (QTY) | Fee schedules compete with quoting rules, and nothing says whether a value is a default, an override, or still unread by the engine | Groups under Strategy, Venues and Runtime in sentence case; the unit beside the field; a state badge on every field |
| The order book boxes our own quote in a bordered row | The least important thing to read is the heaviest thing on the page | A small "ours" tag on the level |

The same review noted that this direction is a calm dashboard, not a
trading cockpit: a single-screen monitor with a price ladder showing our
quotes against the fair price, PnL with fills overlaid, a persistent
status strip and a dark theme would serve a market maker watching for
hours better than cards that scroll. That layout is now built beside the
Dashboard layout (see "The cockpit, for comparison") so the two can be
judged on the same data. Choosing it is a larger decision, because it
turns on whether Streamlit stays the shell.

## Migration

Production carries the tokens, the header and navigation, the context bar
with its badges and live state, the summary rows, cards, tables, badges
and metrics, the two-sided order book, the risk rows, the health summary
and tiles, and the parameter rows and save bar.

Still to build: the stopped-engine state on the monitor, Health and
Parameters; one name per figure and four metrics on Live; signals as
verdict badges; the fills' horizon switch and identifier toggle; text
colour instead of cell fills in the quality and economics tables; Health
tiles grouped by engine with plain names; the parameter section
navigation and field states; the `ours` tag; and the workspace split
itself, with Research's run library, run detail and Compare.

The split cannot be shown yet. Every replay is recorded to
`<exchange>/<symbol>/replay.sqlite`, and `dashboard/data/engines.py`
opens only `live.sqlite`, so no replay has ever appeared in the dashboard.
Reading both recordings is the first production step, before any of the
Research layout. Validate each stage with real empty, populated, stale and
stopped recordings, and preserve the existing dashboard's functional
tests.
