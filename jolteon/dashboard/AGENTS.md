# Dashboard UI work

Read `UI_GUIDELINES.md` before creating or changing dashboard UI. It holds
the rules a screen keeps whatever it looks like - what may never be said
of the data, how numbers, colour and states behave, the accessibility
floor - and the review checklist.

The look itself is a choice, and choices live with `static/prototype/`:
its `styles.css` is the reference for every colour and measure, and its
README describes the current direction - workspaces, page anatomy, type
and spacing, each component's shape - and the reviews behind it. Change a
choice there first, then in production. Extend shared UI components before
introducing page-specific variants, and record any deliberate deviation
and its reason in the change description.

The prototype is a standalone mock with illustrative data, not a production
data source. Do not connect its demo parameter actions to an engine or use
its fixture values as trading defaults. Production behavior and repository
architecture rules remain authoritative during migration.
