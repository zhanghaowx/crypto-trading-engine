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

The workspace switch; the engine selection, where ETH/USD is an engine that
has stopped and shows how the monitor, Health and Parameters say so; the
Live/Paused control in the monitor's strip; the ladder's `ours` tags and
the fair price drawn through it; the fills' side filter, markout horizon
switch and identifier toggle; the Health preview states, including the
populated error log and a component going down; the parameter scope
switch and the state badge on every field (default, inherited, override,
pending, stored and awaiting the engine); parameter edit/review/apply/
revert with each change's scope named in the review; the Runs source
filter; opening a run from the table; a replay's capture link back to the
run that recorded its data; and Compare with two runs over one window and
then over two.

## The current direction: the cockpit

Everything in this section is a choice. It can be revisited, and a
redesign starts by changing it here. The direction was chosen on
2026-09-26, after a card layout and the cockpit were built side by side
on the same sample data and compared; the cockpit showed more of what a
market maker watches in less room, and became the whole prototype.

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
   no page repeats its name as a heading of its own. Only the style guide,
   a document rather than a screen, keeps a heading.
2. A status strip: one row of labelled cells carrying the scope, the mode,
   the freshness or the data window, and the figures a reader checks
   first. It replaces both the context bar and the row of metric tiles,
   and wraps onto a second row only when the window is too narrow for one.
3. Panels in an aligned grid, sized so the monitor fits one screen at a
   desktop width. Nothing a market maker watches is below the fold.
4. Tables and detail below, dense and ruled between rows.

### Type, spacing and shape

One sans-serif family throughout, with system fallbacks; hierarchy comes
from weight, not from a second family. The scale is a step below a
reading page's, because this is watched for hours at arm's length and the
room goes to the numbers.

| Role | Treatment |
| --- | --- |
| Document heading | 26 / 600, style guide only |
| The panel's figure | 26 / 500, tabular |
| Card heading | 13 / 600, the same on every card |
| Body and controls | 12 / 400 to 500 |
| Strip label and table header | 10 / 500 to 600, letter-spaced, secondary |
| Prices, quantities, identifiers | monospace, tabular |

One spacing scale (4, 8, 12, 16, 24, 32) with no values between its
steps. Card insets are 12 to 16px, the grid gap 16px, a table or ladder
row 26 to 32px. Content has a maximum width, and a table never stretches
the page past it. Cards have one radius (10px), controls another (6px),
badges a third (4px). Borders separate surfaces; there are no decorative
shadows. Slate is the one palette.

### The monitor

Three columns under the strip. The **position panel** on the left: the
position as the one big figure, its value at mid and its share of the
limit, then the PnL broken into cash flow, inventory and fees, the fills
by side, each fair-price signal's verdict and contribution, and every
component's state. The **price ladder** in the middle: one column of
prices with the market's bids and asks on either side, depth shading from
cumulative size, our resting quotes tagged `ours` at their level, the mid
and spread between the sides, and the adjusted fair price drawn as a
dashed line through the ladder, so where we quote and where we think the
price is are read together; execution quality by side sits under it. On
the right, **the PnL line with every fill on it**, buys under the line and
sells above, and the **fills** table: one signed column switched by
horizon, identifiers behind a toggle, the symbol left to the strip, and a
horizon that has not passed yet shown as `–`.

The strip carries the engine and its run, the feed's pulse with the
Live/Paused control, the position against its limit, marked PnL, our two
quotes with the fair price beside them, and how many components are
reporting. A stopped engine drains the pulse, says when it stopped, marks
the ladder as its last snapshot and the chart as final, and a neutral
notice above the grid links to the finished run in Research.

### Health

Health reads every engine, so its strip carries the totals - engines
running, components down, recorded errors, the heartbeat timeout, the
snapshot time - and each engine gets a card of its own: the run, its
mode and when it started or stopped in the head, and a table of its
components with plain names (Market making, Paper execution, Public feed,
Parameters), their kind, state, last heartbeat and heartbeat history. A
stopped engine's components say they stopped with it. The navigation dot
on Health appears only while a component is down, and the error log sits
below with an explicit empty state.

### Parameters

Parameters carries the monitor's strip, then a scope strip: the symbol
the edits apply to, whether they reach a running engine or wait for a
stopped one to start, and how often the engine polls. Selected groups
from the production catalog sit under the part of the engine each one
configures - Strategy, Venues, Runtime - in sentence case. Each field has
a persistent label, a state badge, a one-line explanation and its unit
beside the control. The save bar counts pending changes and the review
names each change's scope.

### Research

Runs opens on a strip with the engine, the source filter and the
library's figures, then the table of finished runs. Run detail's strip
carries the run, its two mode badges and status, a replay's capture link,
the data window, the wall clock spent, and the run's figures; below it
sit execution economics and quality on the left, the frozen parameter set
with the current live value beside each and the reading notes on the
right. Compare's strip carries both runs, whether they read one window,
and run B's figures with their delta against A, coloured only for PnL
where the direction means better or worse; a banner says so when the
windows differ.

## Why it looks this way

Two reviews of the production dashboard at `http://localhost:8501`, with
the direction each finding led to.

### Before the migration

Live, Health, and Parameters were inspected in rendered screenshots. The
Post-trade browser capture was still loading its session card; the review
of its completed content is based on the source.

| Behaviour then | Effect | Direction |
| --- | --- | --- |
| Live starts with run metadata; Health starts directly with cards; Parameters starts with tabs | Page hierarchy changes during navigation | A shared anatomy: navigation, strip, panels, then detail |
| Live places a tall order book beside a short risk card | Large unused space and session results below the fold | One screen: position, ladder, PnL with fills, side by side |
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
| Live shows a stopped engine with a Live feed badge, a green pulse and "Refreshing every 5 s"; Health lists its four components as down; Parameters says an edit reaches the running engine | Three pages say something is running when nothing is, and the navigation wears an alert for an engine that was switched off | Stopped is its own quiet state: the pulse drained beside when it stopped, a Stopped badge, a neutral notice linking to the finished run in Research, components that stopped with the engine, and no alert dot |
| Live's summary is six bare numbers - Total PnL 2.54, Net cash flow 271.23, Inventory value -268.69 - and Post-trade calls the same 2.54 Marked PnL | No currency, no sign, the parts of a total beside it as peers, and two names for one figure | The strip's figures with units and signs; cash flow and inventory as rows under marked PnL in the panel; the position as the panel's one big figure; one name on every page |
| Risk limits stands alone beside a tall order book | A quarter of the screen is empty | The limit is a bar under the position; the ladder takes the middle column |
| Fair price signals renders "No usable signal yet" as a red table row | A signal still warming up looks like a failure | A neutral verdict badge beside each signal's contribution, and "–" where there is none yet |
| Recent fills has fourteen columns: two identifiers, the symbol, and four markout horizons | Too wide to scan, and the symbol repeats the context bar | One signed column with a horizon switch; identifiers behind a toggle; the symbol only in the strip |
| Trade quality and Execution economics fill every cell red or green | A table of ordinary results reads as a heat map of alarms | Colour on the signed figure only |
| Health nests its tiles inside a card, names them after classes (MockExecutionService), and reports local time | Double framing, code names, and a second clock | A card per engine with a table of its components under plain names, UTC |
| Parameters lists nineteen groups at equal weight in title case, with the unit in the label (QTY) | Fee schedules compete with quoting rules, and nothing says whether a value is a default, an override, or still unread by the engine | Groups under Strategy, Venues and Runtime in sentence case; the unit beside the field; a state badge on every field |
| The order book boxes our own quote in a bordered row | The least important thing to read is the heaviest thing on the page | A small "ours" tag on the level, and the fair price drawn through the ladder |

The same review noted that the migrated dashboard was a calm reading
page, not a trading cockpit. A cockpit was built beside it on the same
sample data - one screen, a ladder with our quotes against the fair
price, PnL with fills overlaid, a persistent strip - and the two were
compared. The cockpit showed more of what a market maker watches in less
room, and on 2026-09-26 it became the direction.

## Migration

Production carries the tokens, the header and navigation, the context bar
with its badges and live state, the summary rows, cards, tables, badges
and metrics, the two-sided order book, the risk rows, the health summary
and tiles, and the parameter rows and save bar. From the second review it
carries: four named metrics on Live under the names Post-trade uses; the
fills' horizon switch and identifier toggle; signals as verdict badges;
the signed figure coloured rather than its cell; the `ours` tag; and
Parameters with sectioned groups, the unit beside the field, and a badge
on every field. The stopped-engine state and Health's grouping by engine
are under way.

The cockpit itself is not a styling pass on those cards. A ladder, a
chart with fill markers, a status strip that replaces the metric tiles,
and a three-column grid that fits one screen fight Streamlit's page
model: vertical blocks, reruns and thin CSS hooks. Carrying the direction
into production is a decision about the shell - bending Streamlit to it,
or giving this prototype a read-only source for the recordings and
letting it be the dashboard - and that decision is still open. The
workspace split waits on it too: every replay is recorded to
`<exchange>/<symbol>/replay.sqlite`, and `dashboard/data/engines.py`
opens only `live.sqlite`, so reading both recordings is the first step
towards Research whichever shell is chosen.
