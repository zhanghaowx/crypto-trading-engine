# Dashboard card execution

A `Card.id` is stable even when its title changes. IDs must be unique on
one page and must not use Streamlit's reserved fragment keys `app` or
`fragment`. Live and Health call `render_cards` directly; each visible
card registers its own named Streamlit fragment. Timer ticks, pagination,
manual refresh, and opening/dismissing details target that card alone.
The fragment callbacks execute sequentially; this is isolation, not
parallel background work.

`refresh=False` disables a card's timer. `refresh_interval=None` uses the
viewer interval; an explicit interval overrides it. Global auto-refresh
off disables all timers, including cards with an override. The independent
refresh button still works; `manual_refresh=False` omits that button.

Hidden cards are filtered before fragment registration and row placement.
They perform no load, accent, body, action, details, or chart work and do
not accrue metrics. Showing them resumes normal execution. Collapse is a
browser-only expander action: its contents remain live on the server.

## Loading and failure isolation

Simple cards keep zero-argument render callbacks. With `load=...`, a card
loads one model per execution and passes that same object to `body`,
`actions`, and callable `accent`. Details replace the body; the dialog
loads its own fresh model on each execution and passes it to `details`.
Orders & PnL uses this boundary to share fills, positions, fees, and realized
PnL rather than repeating acquisition across its renderers. This is one
logical load, not a SQLite transaction across all source queries.

A loader shows a card-local loading indicator. An ordinary exception in
loading or rendering replaces partial output with a card-specific error
and retry/hide controls, and logs the traceback. Siblings continue to
render. Retrying or a later timer tick can recover without a page reload.
Streamlit's rerun/stop control signals propagate instead of being treated
as failures.

## Measuring cost

Session-local `st.session_state['_card_metrics'][card_id]` holds:

- `refresh_count` and `last_refresh_at` (UTC), including failed attempts;
- `load_ms`, `render_ms`, and `total_ms` for the last execution;
- cumulative `error_count`.

The `jolteon.app.card` logger emits these metrics at DEBUG level. They are
not displayed on the normal dashboard. Hidden cards retain their previous
metrics without changing them. Dialog renders count as executions of their
owning card; opening details does not also render the body.

Load time includes source cache lookups and loader computation. It does
not count physical SQLite reads separately. For legacy cards without an
explicit loader, data reads inside their callbacks fall under render time.
Total time measures server execution, not browser painting or network
latency. Source caches keep their existing freshness policy; manual refresh
does not globally invalidate caches or force a physical database read.

## Whole-page rerun audit

The following deliberately affect more than one card:

- Navigation changes pages. The Live engine selector changes the database
  context and intentionally executes all visible cards.
- Hiding/unhiding changes row packing and timer registration, so it needs
  a full run. Hiding from a failed dialog also closes that dialog.
- The separate Health navigation watcher requests a full run only when
  the alert dot changes between present and absent. Unchanged timer ticks
  do not rerun the page. The watcher remains active even with all cards
  hidden and stops when global auto-refresh is off.
- Switching Parameters tabs changes page content. Controls inside each
  Parameters tab use that tab's fragment; viewer settings apply when the
  reader returns to Live or Health and its fragments are registered again.

There is no periodic whole-app refresh. Dialog dismissal explicitly targets
its owning card. Browser reload remains an intentional full app restart.

## Regression coverage

`tests/app/test_card_execution.py` queues real Streamlit fragment/widget
requests into a single ScriptRunner, retaining fragment storage between
requests. Ordinary AppTest `.run()` calls create fresh runners, so those
alone cannot establish independent execution. The contract tests cover
sibling call counts and unchanged metrics, shared model identity, hiding,
unhiding, manual refresh with auto-refresh disabled, failure/recovery,
details, and global engine changes. Existing renderer and layout tests
continue to cover production cards, stable IDs, and half-width repacking.
