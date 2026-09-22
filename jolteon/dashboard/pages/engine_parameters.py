"""
Editor for the tunables the trading engine reads.

Every widget on this page is built from what a parameter group declares,
so adding a tunable to the engine needs no change here: the new field
arrives with its own bounds, units and description already attached.

A value can be set for every symbol or for one of them, which is how a
size or an edge suited to one instrument is kept away from another. The
page resolves a symbol's value the way the engine does - the symbol's own
value, else the one set for every symbol, else what the field declares -
so what is shown here is what the engine will read.
"""

import re
from dataclasses import dataclass
from typing import Any

import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.sqlite import read_table
from jolteon.dashboard.ui.cards import card_grid, surface_rule
from jolteon.dashboard.ui.primitives import BadgeColor, slug
from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_change_result import (
    REJECTED,
    TAKEN,
    change_key,
)
from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterDefinition,
    definitions,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterChange,
    ParameterStore,
)

_STAGED = "_staged_parameters"
_SCOPE = "parameter-scope"
_REPORTS = "_engine_parameter_reports"
_ALL_SYMBOLS_LABEL = "All Symbols"

# A field identified by the scope it is set for as well as by its name.
Field = tuple[str, str, str]


def _staged() -> dict[Field, Any]:
    return st.session_state.setdefault(_STAGED, {})


def _widget_key(field: Field) -> str:
    # The scope belongs in the key: a widget keyed by name alone would
    # carry one symbol's value over to the next symbol selected, since
    # Streamlit keeps whatever the key already held.
    symbol, group_name, field_name = field
    return f"param.{symbol or 'all'}.{group_name}.{field_name}"


def _stored_values() -> dict[Field, Any]:
    store = ParameterStore(st.session_state.params_db_path)
    return {
        (o.symbol, o.group_name, o.field_name): o.value for o in store.read()
    }


def _scope_label(symbol: str) -> str:
    return symbol or _ALL_SYMBOLS_LABEL


def _scopes(stored: dict[Field, Any]) -> list[str]:
    """
    Returns: Every scope worth offering - all symbols first, then each
    symbol the store or any engine under the root has seen.

    Taken from what has been run and what has been set, rather than from
    a list to maintain, so pointing an engine at a new symbol is enough
    to make that symbol tunable here.

    Every engine, not just the one whose recording the rest of the
    dashboard is reading: a symbol is tunable while its own engine runs,
    whichever engine the reader happens to be looking at.
    """
    selected_exchange = st.session_state.get("exchange", "Kraken")
    symbols = {symbol for symbol, _, _ in stored if symbol != ALL_SYMBOLS}
    symbols.update(
        engine.symbol
        for engine in engine_databases(st.session_state.root)
        if engine.exchange == selected_exchange
    )
    return [ALL_SYMBOLS, *sorted(symbols)]


def _group_has_been_read(report: Any) -> bool:
    return (
        report.current_revision is not None
        and report.last_read_revision is not None
        and report.last_read_revision >= report.current_revision
    )


def _unsettled(report: Any) -> int:
    """Rank rejection, unknown status, and unread groups ahead of reads."""
    if report.status == REJECTED:
        return 3
    if report.status != TAKEN:
        return 2
    return 0 if _group_has_been_read(report) else 1


def _engine_reports() -> dict[str, Any]:
    """Join field results to group revisions within each engine.

    For shared parameters, display the least settled response across the
    selected exchange's engines. Revisions from different engines must
    never be combined: each engine has its own snapshot counter.
    """
    reports: dict[str, Any] = {}
    selected_exchange = st.session_state.get("exchange", "Kraken")
    for engine in engine_databases(st.session_state.root):
        if engine.exchange != selected_exchange:
            continue
        results = read_table(engine.path, "parameter_change_result")
        if results.empty or "key" not in results.columns:
            continue
        revisions = read_table(engine.path, "parameter_group_revision")
        if revisions.empty:
            results = results.assign(
                current_revision=None, last_read_revision=None
            )
        else:
            results = results.merge(
                revisions[
                    ["group_name", "current_revision", "last_read_revision"]
                ],
                on="group_name",
                how="left",
                validate="many_to_one",
            )
        for report in results.itertuples():
            seen = reports.get(report.key)
            if seen is None or _unsettled(report) > _unsettled(seen):
                reports[report.key] = report
    return reports


def _current(field: Field, definition: ParameterDefinition, stored):
    if field in _staged():
        return _staged()[field]
    if field in stored:
        return stored[field]
    return _inherited(field, definition, stored)


def _inherited(field: Field, definition: ParameterDefinition, stored):
    _, group_name, field_name = field
    shared = (ALL_SYMBOLS, group_name, field_name)
    if shared in _staged():
        return _staged()[shared]
    return stored.get(shared, definition.default)


def _presentable(
    definition: ParameterDefinition, value: Any
) -> tuple[Any, Any]:
    """
    Returns: A value the widget will accept, and whatever had to be set
    aside to get there.

    A store can hold a value this page cannot render - a field's bounds
    may have been tightened after it was pushed, or something may have
    written to the store directly. The engine answers that by refusing
    the value and carrying on, and so does this: the widget shows the
    nearest value it can take and the field says what is really stored,
    rather than the whole page failing over one field.
    """
    try:
        coerced = definition.value_type(value)
    except (TypeError, ValueError):
        return definition.default, value

    if definition.choices and coerced not in definition.choices:
        return definition.default, value
    if definition.minimum is not None and coerced < definition.minimum:
        return definition.value_type(definition.minimum), value
    if definition.maximum is not None and coerced > definition.maximum:
        return definition.value_type(definition.maximum), value
    return coerced, None


def _shown(definition: ParameterDefinition, value: Any) -> str:
    # Its own format, or a tight bound like 0.00001 reads as 1e-05.
    if definition.number_format and isinstance(value, float):
        return definition.number_format % value
    return str(value)


def _definition(group_name: str, field_name: str) -> ParameterDefinition:
    return next(
        definition
        for group in GROUPS
        if group.__name__ == group_name
        for definition in definitions(group)
        if definition.name == field_name
    )


def _replaced(field: Field, stored: dict[Field, Any]) -> str:
    """
    The value an edit is leaving behind: what an engine reads for this
    field while the edit is still staged, which is the field's own stored
    value, else the one set for every symbol, else what it declares.
    """
    _, group_name, field_name = field
    definition = _definition(group_name, field_name)
    if field in stored:
        return _shown(definition, stored[field])
    shared = (ALL_SYMBOLS, group_name, field_name)
    return _shown(definition, stored.get(shared, definition.default))


@dataclass(frozen=True)
class _Note:
    """What a field has to say about itself beyond its value."""

    label: str
    color: BadgeColor
    icon: str | None = None
    caption: str | None = None


def _unusable_note(definition: ParameterDefinition, stored: Any) -> _Note:
    allowed = ""
    if definition.minimum is not None and definition.maximum is not None:
        allowed = (
            f" Allowed: {_shown(definition, definition.minimum)}"
            f" to {_shown(definition, definition.maximum)}."
        )
    elif definition.choices:
        allowed = f" Allowed: {', '.join(map(str, definition.choices))}."
    return _Note(
        "Not usable",
        "red",
        ":material/error:",
        caption=(
            f"Stored as {stored}, which this parameter cannot take."
            f"{allowed} An engine reading this store refuses it and keeps "
            f"the value it already had."
        ),
    )


def _on_change(field: Field, definition: ParameterDefinition) -> None:
    value = st.session_state[_widget_key(field)]
    _staged()[field] = definition.value_type(value)


def _card_key(group: type) -> str:
    return f"param-card-{slug(group.__name__)}"


def _group_title(group_name: str) -> str:
    bare = group_name.removesuffix("Parameters")
    return " ".join(re.findall(r"[A-Z][a-z0-9]*", bare))


def _field_label(definition: ParameterDefinition) -> str:
    label = definition.name.replace("_", " ").capitalize()
    if definition.unit:
        label = f"{label} ({definition.unit})"
    return label


def _staged_label(group_name: str, field_name: str) -> str:
    return (
        f"{_group_title(group_name)} · {field_name.replace('_', ' ')}"
    ).title()


_SUMMARY_KEY = "staged-summary"

_SUMMARY_NAME_HEADROOM = 1.25


def _summary_rule() -> str:
    """
    Widens the summary's name column, sized from the whole catalog rather
    than from the rows on screen: a width taken from what happens to be
    staged moves every time a row is added or dropped, and a table that
    resizes under the reader as they work is harder to read.
    """
    longest = max(
        len(_staged_label(group.__name__, definition.name))
        for group in GROUPS
        for definition in definitions(group)
    )
    characters = round(longest * _SUMMARY_NAME_HEADROOM)
    return (
        f"<style>"
        f".st-key-{_SUMMARY_KEY} th:first-child,"
        f" .st-key-{_SUMMARY_KEY} td:first-child"
        f" {{ min-width: {characters}ch; }}"
        f"</style>"
    )


def _widget(field: Field, definition: ParameterDefinition, value) -> None:
    # The label and its tooltip are on the row above, where the field's
    # state sits beside them.
    label = _field_label(definition)
    key = _widget_key(field)
    args = (field, definition)

    if definition.choices:
        options = list(definition.choices)
        st.selectbox(
            label,
            options=options,
            index=options.index(value),
            key=key,
            label_visibility="collapsed",
            on_change=_on_change,
            args=args,
        )
    elif definition.value_type is bool:
        st.checkbox(
            label,
            value=bool(value),
            key=key,
            label_visibility="collapsed",
            on_change=_on_change,
            args=args,
        )
    elif definition.value_type is int:
        st.number_input(
            label,
            value=int(value),
            min_value=_as_int(definition.minimum),
            max_value=_as_int(definition.maximum),
            step=int(definition.step or 1),
            key=key,
            label_visibility="collapsed",
            on_change=_on_change,
            args=args,
        )
    elif definition.value_type is float:
        st.number_input(
            label,
            value=float(value),
            min_value=definition.minimum,
            max_value=definition.maximum,
            step=definition.step,
            # Without a format a value like 0.0005 renders as float noise.
            format=definition.number_format,
            key=key,
            label_visibility="collapsed",
            on_change=_on_change,
            args=args,
        )
    else:
        st.text_input(
            label,
            value=str(value),
            key=key,
            label_visibility="collapsed",
            on_change=_on_change,
            args=args,
        )


def _as_int(bound: float | None) -> int | None:
    return None if bound is None else int(bound)


def _state_note(
    field: Field,
    definition: ParameterDefinition,
    stored: dict[Field, Any],
) -> _Note | None:
    """Describe a change result and whether its group has been read."""
    symbol, group_name, _ = field
    if field not in stored:
        inherited = (ALL_SYMBOLS, group_name, definition.name) in stored
        if symbol != ALL_SYMBOLS and inherited:
            return _Note("Inherited", "grey")
        return None

    reports = st.session_state.get(_REPORTS, {})
    row = reports.get(change_key(group_name, definition.name, symbol))
    if row is None:
        return _Note(
            "Not picked up",
            "yellow",
            caption="Stored, but no engine has reported reading it.",
        )
    if row.status == REJECTED:
        return _Note("Rejected", "red", ":material/error:", row.reason)
    if row.status != TAKEN:
        # The engine decides what statuses exist, so one this page has
        # never heard of is passed through as it came.
        return _Note(row.status, "orange")
    if _group_has_been_read(row):
        return None
    return _Note(
        "Not read yet",
        "yellow",
        caption=(
            "Accepted, but no component has read the current parameter group."
        ),
    )


def _field(
    field: Field,
    definition: ParameterDefinition,
    stored: dict[Field, Any],
) -> None:
    usable, unusable = _presentable(
        definition, _current(field, definition, stored)
    )
    note = (
        _state_note(field, definition, stored)
        if unusable is None
        else _unusable_note(definition, unusable)
    )
    _label_row(definition, note)
    _widget(field, definition, usable)
    if note is not None and note.caption:
        st.caption(note.caption)


def _label_row(definition: ParameterDefinition, note: _Note | None) -> None:
    """
    The field's name, and what it has to say about itself beside it.

    A horizontal container rather than columns: a parameter card is
    narrow, and a fixed split would squeeze the name to make room for a
    badge that is usually not there at all.
    """
    with st.container(
        horizontal=True, vertical_alignment="center", gap="small"
    ):
        st.markdown(
            f"{_field_label(definition)}",
            help=definition.description or None,
            width="content",
        )
        if note is not None:
            st.badge(note.label, color=note.color, icon=note.icon)


def _push() -> None:
    store = ParameterStore(st.session_state.params_db_path)
    store.push(
        [
            ParameterChange(group_name, field_name, symbol, value)
            for (symbol, group_name, field_name), value in _staged().items()
        ]
    )
    st.session_state[_STAGED] = {}


def _revert() -> None:
    st.session_state[_STAGED] = {}


def _selected_scope(scopes: list[str]) -> str:
    if len(scopes) == 1:
        return ALL_SYMBOLS
    scope = st.segmented_control(
        "Applies to",
        options=scopes,
        format_func=_scope_label,
        default=ALL_SYMBOLS,
        key=_SCOPE,
        label_visibility="collapsed",
    )
    # A segmented control lets the reader clear their own selection.
    return ALL_SYMBOLS if scope is None else scope


def render() -> None:
    stored = _stored_values()
    st.session_state[_REPORTS] = _engine_reports()
    staged = _staged()
    symbol = _selected_scope(_scopes(stored))

    # Before the cards themselves: a rule arriving after a container has
    # reached the browser shows the canvas through it for a moment first.
    st.html(surface_rule(_card_key(group) for group in GROUPS))

    for group in card_grid(GROUPS, key="parameter-cards", key_fn=_card_key):
        st.markdown(f"**{_group_title(group.__name__)}**")
        for definition in definitions(group):
            _field(
                (symbol, group.__name__, definition.name), definition, stored
            )

    if staged:
        # A markdown table, not `st.dataframe`: the data grid is a lazily
        # loaded bundle the browser only fetches the first time a table is
        # shown, so the summary of an edit arrives about half a second
        # after the edit that staged it.
        rows = "\n".join(
            f"| {_staged_label(group_name, field_name)} "
            f"| {_scope_label(scope)} "
            f"| {_replaced((scope, group_name, field_name), stored)} "
            f"| {_shown(_definition(group_name, field_name), value)} |"
            for (scope, group_name, field_name), value in staged.items()
        )
        st.html(_summary_rule())
        with st.container(horizontal=True, horizontal_alignment="center"):
            with st.container(key=_SUMMARY_KEY, width="content"):
                st.markdown(
                    f"| Parameter | Applies to | From | To |\n"
                    f"| --- | --- | --- | --- |\n{rows}"
                )

    with st.container(horizontal=True, vertical_alignment="center"):
        st.button(
            "Commit",
            type="primary",
            disabled=not staged,
            on_click=_push,
            icon=":material/upload:",
        )
        st.button("Revert", disabled=not staged, on_click=_revert)
