# Jolteon design preview

A dependency-free, interactive design proposal for the existing dashboard.
Open `index.html` in a browser, or from the repository root run:

```sh
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 \
  --directory jolteon/dashboard/static/prototype
```

Visit http://localhost:8765. All data is illustrative and parameter changes
affect only in-memory demo state. Reloading resets the demo. The existing
dashboard on port 8501 is unchanged.

## Two workspaces

The header switches between them, and each has a navigation of its own:

- **Trading** - Health, Live monitor, Parameters. One engine reading a live
  feed, right now. It refreshes, says when it last did, and its parameter
  edits are described as reaching the running engine.
- **Research** - Runs, Compare. Every run that has finished, whether it read
  a live feed or a recording. Nothing refreshes, parameters are shown frozen
  as the input the run was handed, and run detail is reached by choosing a
  run rather than from the navigation.

Which workspace a screen belongs to follows from where its market data came
from, not from whether execution was paper or real - that is a badge.

Two engines are configured and only BTC/USD is running. ETH/USD stopped two
days ago, and choosing it shows how a stopped engine is met: the monitor
drains its pulse, says when it stopped and points at the finished run;
Health lists its components as stopped with it rather than down; Parameters
says an edit waits for it to start. Nothing is down when nothing is running.

No page opens with a heading of its own: the navigation names the page, and
the room under it goes to the context bar. Only the style guide, a document
rather than a screen, keeps one.

Try the workspace switch, the engine selection (ETH/USD is the stopped
one), the Live/Paused control on the monitor, the order book's `ours` tag,
the fills' side filter, markout horizon switch and identifier toggle, the
Health preview states across both engines including the populated error
log, the parameter scope switch and the state badge on every field
(default, inherited, override, pending, stored and awaiting the engine),
parameter edit/review/apply/revert with each change's scope named in the
review, the Runs source filter, opening a run from the table, a replay's
capture link back to the run that recorded its data, and Compare with two
runs over one window and then over two.

The palette switcher in the header (Slate / Sage / Morandi) is a comparison
tool, not a proposal in itself: each option swaps the same tokens for a
different neutral base and brand accent, so the layout, contrast, and
content stay identical while only the palette changes. The chosen palette
is remembered in this browser only and does not change which palette
UI_GUIDELINES.md documents as the current default.

`styles.css` owns the prototype tokens and reusable layout styles;
`app.js` owns fixtures, shared rendering, and interactions;
`index.html` owns the document shell. No external fonts or packages load.

The review, production mapping, and future-work checklist are in
[UI_GUIDELINES.md](../../UI_GUIDELINES.md).
