# Jolteon UI guidelines

This document holds the rules a dashboard screen has to keep whatever it
looks like: what may never be said of the data, how numbers, colour and
states behave, and the accessibility floor. It carries no values and no
layouts. Those are choices, and choices live with the standalone
[prototype](static/prototype/index.html): its `styles.css` is the
executable reference for every colour and measure, and its
[README](static/prototype/README.md) describes the current direction -
the workspaces, the page anatomy, the type and spacing scale, each
component's shape - and records the reviews of the production dashboard
that led to it.

The sorting test for new material: a rule belongs here if it would
survive a redesign. A contrast ratio, the sign convention for money, or
"never call stopped data live" outlives any palette or layout. A font
size, a metric count or a heading decision does not, so it belongs in the
prototype. When a rule and a rendering disagree, the prototype is right
about what a thing looks like and this document is right about what may
never happen. A value stated in both places is a bug in this document.

Status: the direction is the cockpit the prototype shows, chosen on
2026-09-26 over the card layout production carries. Production has the
tokens, the shared components and the second review's card-level fixes;
carrying the cockpit itself into production is a decision about the
shell that is still open, and the README's migration section says so.
The workspace split waits on reading replay recordings.

## Say only what is true

- Never label recorded, paused or stopped data as live. Only a feed being
  read right now may pulse or say when it last updated. A pause keeps the
  indicator in place and drains it. A stopped engine says when it stopped
  and where its finished run can be read.
- A stopped engine is not a set of down components. When nothing is
  running, nothing is down: stopped is a neutral state and raises no
  alert.
- An error recorded against a component is not the component being down.
  An alert follows the component's heartbeat, not the log.
- A finished run's numbers never refresh. Where cards refresh on their own
  timers, each keeps its own freshness; a page-level time must not imply
  every card refreshed. While loading or after an error, keep the last
  successful observation on screen.
- A run states its execution mode (paper or real) and its market-data
  mode (live feed or replay) separately. A replay states both clocks, the
  data window it read leading the wall clock it spent, and links to the
  run that captured its data. A finished live session has one clock.
- Health reads every engine; never imply it shares the engine selected on
  another page.
- Parameters names its edit scope - all symbols or one - and says whether
  a change reaches a running engine or waits for one to start. Stored is
  not acknowledged: keep default, inherited, overridden, pending, stored
  and engine-acknowledged states distinct. Show every pending change with
  its scope, previous value and proposed value before committing; revert
  restores the stored values; disable commit when nothing has changed or
  any field is invalid; keep pending changes across navigation.
  Validation comes from the real parameter definition. Never write
  parameters into an engine recording.
- Two runs are comparable only over one data window. When the windows
  differ, say so before showing the difference.
- Show a trend only when measured history backs it. Do not invent a
  percentage change, use an unlabeled comparison period, or let a
  decorative sparkline imply data. Depth shading uses the book's actual
  cumulative size, with bid and ask headings visible. A chart's range
  control changes the underlying scope, not only the picture.
- Every time on a page names its timezone, one timezone per view, UTC by
  default.

## Numbers

- One figure has one name on every page. What Live calls marked PnL,
  Research calls marked PnL.
- Money uses two decimals and grouping separators. Signed money puts the
  sign before the currency: `+$128.42`, `−$12.30`. Name the currency; do
  not assume every pair is USD.
- Asset quantities keep the precision that means something; never round a
  small position to zero. Prices follow the instrument's precision.
- An unavailable measurement is `ui.primitives.MISSING` (`–`). Zero is an
  observed value. Post-trade statistics state their measurement coverage,
  and partial data shows the valid rows and names the gap.
- Units live in the column header or beside the field, not inside the
  label. Numeric columns are right-aligned; labels are left-aligned.
- A chart names its series, units, time range and timezone, and has
  meaningful axes.
- Figures that change in place use tabular numerals so they do not
  jitter; dense prices, quantities and identifiers may use a monospace
  stack.

## Colour

The palette has these roles to fill. The prototype defines each value.

| Token | Use |
| --- | --- |
| Canvas | Page background |
| Surface | Cards and controls |
| Text | Headings, numbers, primary actions |
| Secondary text | Supporting text |
| Border | Card separation and table rules |
| Brand accent | Active navigation indicator; decorative only |
| Positive / Positive surface | Positive values, buy labels, healthy status |
| Negative / Negative surface | Negative values, sell labels, errors |
| Warning / Warning surface | Elevated risk, stale data |
| Information / Information surface | Mode badges and keyboard focus |

- Colour never carries a meaning alone. A label, a sign or an icon says
  it; the colour agrees.
- Red and green are data as well as status: a side, a signed outcome, a
  price moving. Keep the semantic hues muted enough that a page of
  ordinary sells does not read as a page of errors. A sell is a side, not
  an error. Independent signal series use slate or blue, not red or green.
- Colour the signed figure, not its container. A positive result does not
  make its card green, and a table of ordinary results does not fill its
  cells.
- Colour a delta only where its direction means better or worse. A
  smaller fee bill is not a loss.
- Normal is quiet. Healthy status, "no errors recorded", a signal still
  warming up or too weak to use, and a stopped engine are neutral.
  Warning is for elevated risk and stale data; negative is for faults.
- The brand accent is decorative: dark text on the brand surface, never a
  small-text colour or a primary button fill.
- Contrast is at least 4.5:1 for normal text and 3:1 for large text and
  meaningful control indicators.

## States

| State | Required treatment |
| --- | --- |
| Loading | Reserve the content's space; label the operation; keep the last successful data when there is some |
| Empty | Neutral title, why there is no data, and the next useful action if one exists |
| Stale | Warning label, last observation time, and the affected scope |
| Stopped | Neutral badge, when it stopped, and where the finished run is; nothing on the page may read as live |
| Error | Plain explanation, the affected component, and a real recovery action if there is one |
| Success | Brief confirmation near the task; do not move focus or disrupt navigation |
| Partial data | Show the valid rows and name the missing coverage |
| Disabled | Explain the dependency when it is unclear; never rely on a faded appearance alone |

Risk band boundaries are domain behaviour, not styling: below 70% is OK,
70% to below 90% is elevated, 90% and above is near limit. A styling
change does not move them.

## Accessibility and layout

- Use native buttons, links, forms, headings, table headers and labels.
  Every icon action has an accessible name. Keyboard focus is visible and
  follows the visual order. A dialog moves focus into itself, closes on
  Escape and restores focus afterwards. Save feedback is announced without
  moving focus.
- Targets are at least 36px high, preferably 44px for touch, even inside a
  dense table: grow the hit area with padding absorbed by a negative
  margin rather than shrinking it to fit the row. Compact controls need
  clear separation.
- Respect reduced-motion preferences. Check keyboard-only navigation and
  200% zoom before a layout ships.
- At narrow widths, cards stack and scope controls wrap. A wide table
  scrolls inside its container; the document itself never overflows
  horizontally. Text is never shrunk to fit.
- A usable layout must not depend on a font loading over the network.

## Streamlit implementation

- Streamlit's own widgets are themed from `.streamlit/config.toml`. Any
  stylesheet of ours names a `static/tokens.css` token, never a hex;
  `tests/dashboard/static/test_tokens.py` holds the token sheet to the
  prototype's values. The few literals `ui/primitives.py` has to hand out
  stay in step with the theme.
- Custom CSS belongs in `static`, scoped to stable keys, with its
  limitation documented. No unscoped DOM overrides.
- Extend shared `ui` components before styling a page. Card-specific
  content stays in `cards`; a calculation that would make sense without
  Streamlit stays in `analysis`. Reuse the card lifecycle, refresh
  behaviour, run selection and read-only recording access. Styling never
  changes domain semantics.
- Visual consistency is reviewed against the prototype with screenshots;
  the coverage suite does not assert it.

## Review checklist

- [ ] Every label on the page is true of the data under it: live, paused,
      stopped or finished, and the timezone is named.
- [ ] One name per figure across pages; numbers carry units, signs,
      precision and `–` for missing values consistently.
- [ ] Colour agrees with a label, sign or icon; containers are not filled
      for ordinary results; normal states are neutral.
- [ ] Loading, empty, stale, stopped, error and partial-data behaviour are
      considered.
- [ ] Keyboard focus, accessible names, contrast and narrow layouts are
      checked.
- [ ] Settings keep scope, validation, review and engine acknowledgement.
- [ ] Existing components and tokens are reused; a deliberate deviation
      from the prototype's direction is recorded in the change description.
- [ ] Desktop and mobile screenshots are reviewed where layout changes.
- [ ] `uv run poe architecture` and `uv run poe test` pass; blockers are
      recorded.
