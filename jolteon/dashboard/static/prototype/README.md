# Jolteon design preview

A dependency-free, interactive design proposal for the existing dashboard.
Open `index.html` in a browser, or from the repository root run:

```sh
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 \
  --directory jolteon/dashboard/static/prototype
```

Visit http://localhost:8765. The Live, Health, Parameters, Post-trade, and
Style guide links work without a server-side application. All data is
illustrative and parameter changes affect only in-memory demo state.
Reloading resets the demo. The existing dashboard on port 8501 is unchanged.

Try engine selection, Live tabs, chart windows, fill filters and CSV export,
the Health state selector, parameter edits followed by review/apply/revert,
compact tables under Dashboard settings, and completed-run selection.

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
