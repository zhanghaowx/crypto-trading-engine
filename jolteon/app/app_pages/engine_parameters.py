"""
Editor for the tunables the trading engine reads.

Every widget on this page is built from what a parameter group declares,
so adding a tunable to the engine needs no change here: the new field
arrives with its own bounds, units and description already attached.
"""

import re
from typing import Any

import streamlit as st

from jolteon.app.components import card_grid, card_surface_rule
from jolteon.app.data import read_table
from jolteon.engine.core.parameter.parameter_applied import (
    REJECTED,
    TAKEN,
    applied_key,
)
from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterDefinition,
    definitions,
)
from jolteon.engine.core.parameter.parameter_store import (
    ParameterOverride,
    ParameterStore,
)

_STAGED = "_staged_parameters"


def _staged() -> dict[tuple[str, str], Any]:
    return st.session_state.setdefault(_STAGED, {})


def _widget_key(group_name: str, field_name: str) -> str:
    return f"param.{group_name}.{field_name}"


def _stored_values() -> dict[tuple[str, str], Any]:
    store = ParameterStore(st.session_state.params_db_path)
    return {
        (o.group_name, o.field_name): o.value
        for o in store.read()
        if o.symbol == ALL_SYMBOLS
    }


def _engine_state() -> dict[str, Any]:
    """
    What the engine last said it did with each pushed parameter. Absent
    until an engine has run against this store.
    """
    applied = read_table(st.session_state.db_path, "parameter_applied")
    if applied.empty or "key" not in applied.columns:
        return {}
    return {row.key: row for row in applied.itertuples()}


def _current(group_name: str, definition: ParameterDefinition, stored):
    key = (group_name, definition.name)
    if key in _staged():
        return _staged()[key]
    return stored.get(key, definition.default)


def _on_change(group_name: str, definition: ParameterDefinition) -> None:
    value = st.session_state[_widget_key(group_name, definition.name)]
    _staged()[(group_name, definition.name)] = definition.value_type(value)


def _card_key(group: type) -> str:
    return "param-card-" + re.sub(
        r"[^a-z0-9]+", "-", group.__name__.lower()
    ).strip("-")


def _group_title(group_name: str) -> str:
    bare = group_name.removesuffix("Parameters")
    words = re.findall(r"[A-Z][a-z0-9]*", bare)
    return " ".join(words[:1] + [w.lower() for w in words[1:]])


def _field_label(definition: ParameterDefinition) -> str:
    label = definition.name.replace("_", " ").capitalize()
    if definition.unit:
        label = f"{label} ({definition.unit})"
    return label


def _widget(group_name: str, definition: ParameterDefinition, value) -> None:
    label = _field_label(definition)
    key = _widget_key(group_name, definition.name)
    described = definition.description or None
    args = (group_name, definition)

    if definition.choices:
        options = list(definition.choices)
        st.selectbox(
            label,
            options=options,
            index=options.index(value),
            key=key,
            help=described,
            on_change=_on_change,
            args=args,
        )
    elif definition.value_type is bool:
        st.checkbox(
            label,
            value=bool(value),
            key=key,
            help=described,
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
            help=described,
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
            help=described,
            on_change=_on_change,
            args=args,
        )
    else:
        st.text_input(
            label,
            value=str(value),
            key=key,
            help=described,
            on_change=_on_change,
            args=args,
        )


def _as_int(bound: float | None) -> int | None:
    return None if bound is None else int(bound)


def _state_badge(
    group_name: str,
    definition: ParameterDefinition,
    stored: dict[tuple[str, str], Any],
) -> None:
    """
    What the engine did with this field, as it reported it. Nothing is
    shown for a field left at its declared default, since there is
    nothing to have picked up.
    """
    if (group_name, definition.name) not in stored:
        return

    engine = st.session_state.get("_engine_parameter_state", {})
    row = engine.get(applied_key(group_name, definition.name, ALL_SYMBOLS))
    if row is None:
        st.badge("not picked up", color="yellow")
        st.caption("Stored, but no engine has reported reading it.")
        return
    if row.status == REJECTED:
        st.badge("rejected", color="red", icon=":material/error:")
        st.caption(row.reason)
    elif row.status != TAKEN:
        st.badge(row.status, color="orange")
    elif row.observed_revision >= row.revision:
        st.badge("applied", color="green", icon=":material/check:")
    else:
        st.badge("not read yet", color="yellow")
        st.caption("Stored, but the component has not looked since.")


def _push() -> None:
    store = ParameterStore(st.session_state.params_db_path)
    store.push(
        [
            ParameterOverride(group_name, field_name, ALL_SYMBOLS, value)
            for (group_name, field_name), value in _staged().items()
        ]
    )
    st.session_state[_STAGED] = {}


def _revert() -> None:
    st.session_state[_STAGED] = {}


def _reset() -> None:
    ParameterStore(st.session_state.params_db_path).reset()
    st.session_state[_STAGED] = {}


def render() -> None:
    st.caption(
        "Changes are staged here and reach the engine only when you push "
        "them. The engine picks them up within its poll interval."
    )

    stored = _stored_values()
    st.session_state["_engine_parameter_state"] = _engine_state()
    staged = _staged()

    with st.container(horizontal=True, vertical_alignment="center"):
        st.button(
            f"Push {len(staged)} change{'' if len(staged) == 1 else 's'}",
            type="primary",
            disabled=not staged,
            on_click=_push,
            icon=":material/upload:",
        )
        st.button("Revert", disabled=not staged, on_click=_revert)
        st.button("Reset all to defaults", on_click=_reset)

    if staged:
        st.dataframe(
            [
                {
                    "Parameter": f"{group_name}.{field_name}",
                    "From": str(
                        stored.get((group_name, field_name), "default")
                    ),
                    "To": str(value),
                }
                for (group_name, field_name), value in staged.items()
            ],
            hide_index=True,
            width="stretch",
        )

    # Before the cards themselves: a rule arriving after a container has
    # reached the browser shows the canvas through it for a moment first.
    st.html(card_surface_rule(_card_key(group) for group in GROUPS))

    for group in card_grid(GROUPS, columns=3, key_fn=_card_key):
        st.markdown(f"**{_group_title(group.__name__)}**")
        for definition in definitions(group):
            _widget(
                group.__name__,
                definition,
                _current(group.__name__, definition, stored),
            )
            _state_badge(group.__name__, definition, stored)
