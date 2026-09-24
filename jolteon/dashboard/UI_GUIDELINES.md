# Jolteon UI guidelines

Status: proposed visual direction, demonstrated by the standalone
[interactive prototype](static/prototype/index.html). Production screens have
not yet been migrated. Apply this guide to new and revised UI work; migrate
shared components before introducing page-specific versions of these styles.

## Review of the current dashboard

Reviewed the source and the running dashboard at `http://localhost:8501`.
Live, Health, and Parameters were inspected in rendered screenshots. The
Post-trade browser capture was still loading its session card; the review of
its completed content is based on the source.

| Current behavior | Effect | Proposed direction |
| --- | --- | --- |
| Live starts with run metadata; Health starts directly with cards; Parameters starts with tabs | Page hierarchy changes during navigation | Shared title, purpose, scope bar, then content |
| Live places a tall order book beside a short risk card | Large unused space and session results below the fold | Summary metrics first; compact bid/ask columns beside risk and signals |
| Parameters displays many groups in three masonry columns | All settings compete for attention; commit controls sit after a long form | Group navigation, aligned field rows, visible change summary |
| Healthy cards have a strong green edge; no-error/no-fill states use blue alert panels | Normal operation receives too much visual emphasis | Neutral surfaces and compact status badges; quiet empty states |
| Card CSS names Space Grotesk, the theme defines three font families, and multiple CSS files repeat colors | Changes can drift across cards and pages | One UI family, one number style, shared semantic tokens |
| Several card titles use title case, while parameter labels use sentence case | Inconsistent voice | Sentence case everywhere, preserving proper names and acronyms |
| Run metadata uses UTC while health reports use local time | Readers must translate timestamps across pages | Explicit, consistent timezone within a view; UTC by default |

Keep the existing strengths: shared Card rendering, centralized number
formatting, per-card refresh, visible risk thresholds, run-scoped analysis,
missing-value markers, and staged parameter changes.

## Visual foundation

The prototype's `styles.css` is the executable reference for this proposal.
Do not copy its entire CSS into Streamlit. Map the tokens to native theme
settings and the existing shared UI components during implementation.

| Token | Value | Use |
| --- | --- | --- |
| Canvas | `#F6F7F9` | Page background |
| Surface | `#FFFFFF` | Cards and controls |
| Text | `#20262E` | Headings, numbers, primary actions |
| Secondary text | `#626D7C` | Supporting text |
| Border | `#E2E6EB` | Card separation and table rules |
| Brand accent | `#B59339` | Active navigation indicator; decorative only |
| Positive | `#137552` | Positive values, buy labels, healthy status |
| Positive surface | `#EAF5EF` | Positive badge/depth tint |
| Negative | `#B63E49` | Negative values, sell labels, errors |
| Negative surface | `#FBEEF0` | Negative badge/depth tint |
| Warning | `#946315` | Elevated risk, stale data |
| Warning surface | `#FFF5DF` | Warning panels and badges |
| Information | `#456AAC` | Mode badges and keyboard focus |
| Information surface | `#EDF2FB` | Informational badges |

Use dark text on the gold brand surface; gold is not a small-text color or a
primary button fill. Color accompanies labels, signs, or icons. A sell is a
side, not an error; its text label establishes the meaning.

Use Inter when available, with system sans-serif fallbacks. Do not make font
network access a prerequisite for usable layout. Use tabular numerals for
metrics and a monospace stack for dense prices, quantities, and identifiers.

| Role | Size / weight |
| --- | --- |
| Page heading | 29px / 600 |
| Card heading | 15px / 600 |
| Body and controls | 14px / 400–500 |
| Context and supporting text | 12–13px / 400 |
| Compact table headers and metadata | 10–11px / 500; only for secondary content |
| Summary value | 28px / 500 |

Use a spacing scale of 4, 8, 12, 16, 24, and 32px. Card insets are 20–24px;
section gaps are 20–24px. Desktop page gutters are at least 32px, mobile
18px. Content has a maximum width of 1320px. Cards use a 10px radius,
controls 6px, badges 4px. Use borders rather than decorative shadows.

## Shared page anatomy

1. Persistent navigation: Live, Health, Parameters, Post-trade.
2. One page heading and a short explanation of its purpose.
3. A context bar identifying the scope, mode, run, and observation time.
4. Up to four summary metrics when they help the task.
5. Primary content in aligned columns, then supporting tables and details.

Health is explicitly cross-engine; do not imply that it shares the selected
Live engine. Parameters must name its own edit scope, including whether it
applies to all symbols or one symbol. Post-trade must select a completed run
and distinguish execution mode from market-data mode. A replay identifies its
source recording. Never label historical or paused data as live.

Preserve per-card freshness when independent fragments refresh at different
times. A page-level refresh timestamp must not imply every card refreshed.
Show the last successful observation when loading or errors occur.

## Components

### Cards and metrics

Use the existing `dashboard/ui/cards` abstraction. Card headers share the same
inset, heading style, and action location. Reserve an action area; avoid
absolutely positioning controls over long titles. Keep essential context
visible when details are collapsed. If cards can be hidden, preserve the
existing discoverable way to restore them.

Each metric has a name, value, unit or scope, and optional explanatory line.
Show trends only when backed by measured history. Do not invent a percentage
change or use an unlabeled comparison period. A positive result need not
make the whole card green.

### Tables and charts

Use shared table and formatting primitives. Left-align labels; right-align
numeric headers and cells. Put units in column headers. Use a quiet header
band, horizontal row separators, and no decorative vertical gridlines.

Money uses two decimals and grouping separators. Signed money places the
sign before the currency (`+$128.42`, `−$12.30`). Keep meaningful asset
quantity precision; do not round a small position to zero. Prices follow the
instrument's precision. Preserve `ui.primitives.MISSING` (`–`) for unavailable
measurements; zero is an observed value. Include measurement coverage in
post-trade statistics. Name the currency; do not assume every pair is USD.

Charts need a series label, units, time range and timezone, and meaningful
axes. Chart range controls must change the underlying scope. Keep red/green
for signed outcomes or sides; use slate/blue for independent signal series.
Do not infer data from decorative sparklines. Depth shading must use actual
cumulative book size, with bid and ask headings visible.

### Parameters

Use task groups rather than rendering every catalog group at equal weight.
Preserve access to the full production catalog; the prototype shows selected
groups only. Each field has a persistent label, a unit, and a concise
explanation. Validation must come from the real parameter definition rather
than generic prototype constraints.

Keep default, inherited, overridden, pending, stored, and engine-reported
states distinct. Show all pending changes with scope, previous value, and
proposed value before committing. Revert restores the last stored values.
Disable commit when there are no changes or any field is invalid. Preserve
pending changes across navigation. Stored is not the same as acknowledged
by the engine. Never write parameters to an engine recording.

### Feedback and states

| State | Required treatment |
| --- | --- |
| Loading | Reserve content space; label the operation; retain last successful data when available |
| Empty | Neutral title, why there is no data, and the next useful action if one exists |
| Stale | Warning label, last observation time, and affected scope |
| Error | Plain explanation, affected component, and a real recovery action if available |
| Success | Brief nearby confirmation; do not disrupt navigation |
| Partial data | Show valid rows and explicitly identify missing coverage |
| Disabled | Explain dependency when unclear; do not rely solely on faded appearance |

“No errors recorded” is a normal state. Avoid a large blue alert for it.
Risk band boundaries remain domain behavior: currently below 70% is OK,
70% to below 90% is elevated, and 90% and above is near limit. Do not change
these thresholds as part of a styling task.

## Accessibility and responsive behavior

Use native buttons, links, forms, headings, table headers and labels. Provide
visible keyboard focus and an accessible name for every icon action. Keep
routine focus order aligned with visual order. A dialog must move focus into
it, support Escape, and restore focus after closing. Announce save feedback
without moving focus.

Check 4.5:1 contrast for normal text and 3:1 for large text and meaningful
control indicators. Never rely on color alone. Make targets at least 36px
high, preferably 44px for touch; compact controls need clear separation.
Respect reduced-motion preferences. Check keyboard-only navigation and 200%
zoom as part of production migration.

At narrow widths, stack main cards and wrap scope controls. Summary metrics
can remain two across until their values stop fitting. Wide tables scroll
inside their cards; the document itself must not overflow horizontally.
Group navigation can scroll horizontally. Do not shrink text to fit a table.

## Streamlit implementation and enforcement

- Start with `.streamlit/config.toml` for native theme settings. Keep manual
  semantic values in `ui/primitives.py` synchronized with that theme.
- Extend shared `ui` components before adding styling to a page. Card-specific
  content stays in `cards`; source-independent calculations stay in `analysis`.
- Reuse the existing Card lifecycle, refresh behavior, run selection, and
  read-only recording access. Styling must not change domain semantics.
- Prefer native Streamlit containers, widgets, badges and theme settings.
  Any necessary custom CSS belongs in `static`, scoped to stable keys,
  with its limitation documented. Do not add unscoped DOM overrides.
- Review new UI against the checklist below. The scoped `AGENTS.md` makes
  this guide a required input for future dashboard work; visual consistency
  still requires review and is not asserted by the Python coverage suite.

### Review checklist

- [ ] Page anatomy, scope and timezone follow the shared pattern.
- [ ] Existing components and tokens are reused; no unexplained new variants.
- [ ] Numbers, units, signs, precision and missing values are consistent.
- [ ] Loading, empty, stale, error and partial-data behavior are considered.
- [ ] Keyboard focus, labels, contrast and narrow layouts are checked.
- [ ] Settings retain scope, validation, review and engine acknowledgement.
- [ ] Desktop and mobile screenshots are reviewed where layout changes.
- [ ] Required architecture and test commands run; blockers are recorded.

## Prototype and rollout

Open `static/prototype/index.html` directly, or serve it locally:

```sh
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 \
  --directory jolteon/dashboard/static/prototype
```

Browse `http://localhost:8765`. No dependencies, build step, engine database,
API calls or external assets are required. All fixtures are illustrative.
Controls demonstrate engine selection, fill filtering/export, chart windows,
health states, parameter staging/review/revert, and completed-run selection.
Settings survive page navigation but reset on browser reload.

A palette switcher in the header (Slate / Sage / Morandi) swaps the same
token set between three complete neutral-and-accent combinations, so the
layout and content are held constant while only the palette changes. This
is a side-by-side comparison aid for choosing a direction, not a decision:
the token table above still documents Slate as the current proposal until
one is chosen. Only the neutrals and the brand accent move between the
three; Positive, Negative, Warning and Info keep the hues in that table,
muted for Morandi to match its lower-saturation character.

This is a design artifact, not a replacement Streamlit application. Its
sample fields, charts and status history do not introduce production data
requirements. The wordmark is a proposed treatment; existing brand assets
remain available.

Suggested migration order: theme and shared primitives; page headers and
scope bars; Live layout; Health and its states; Parameters; Post-trade.
Validate each stage with real empty, populated and stale recordings and
preserve the existing dashboard's functional tests.
