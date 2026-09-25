import re
from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.sqlite import as_datetime
from jolteon.dashboard.services.health import errors as error_rows
from jolteon.dashboard.ui.pagination import paginate
from jolteon.dashboard.ui.primitives import SEMANTIC_COLORS, row_key

PAGE_SIZE = 10

_LEVEL_ICONS: dict[str, str] = {
    "ERROR": ":material/error:",
    "CRITICAL": ":material/dangerous:",
}

# The same colors HEARTBEAT_BADGES uses for these levels.
_LEVEL_ACCENTS: dict[str, str] = {
    "ERROR": SEMANTIC_COLORS["orange"],
    "CRITICAL": SEMANTIC_COLORS["red"],
}

# Log entries read as a list of records, not cards - square corners (the
# theme's own `baseRadius` rounds bordered containers and expanders alike)
# read as more list-like here than the app's usual pill shapes.
_SQUARE_ROW_CSS = (
    '[class*="st-key-row-error-"], [class*="st-key-row-error-"] * '
    "{ border-radius: 0 !important; }"
)

# SmartFormatter (jolteon/core/logging/logger.py) bakes
# "[time][logger][level][thread][file:line] - " into `msg` itself, and a
# record formatted by more than one handler can end up carrying it twice.
# This page already shows those fields on their own, so it's stripped back
# to just the message a human wrote.
_FORMATTED_PREFIX = re.compile(r"^(?:\[[^\]]*\]){5}\s-\s")


def _clean_message(msg: str) -> str:
    while True:
        stripped = _FORMATTED_PREFIX.sub("", msg, count=1)
        if stripped == msg:
            return msg
        msg = stripped


def _local_time(seconds: pd.Series) -> pd.Series:
    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    return as_datetime(seconds).dt.tz_convert(local_tz)


def _relative_age(local_time: pd.Timestamp) -> str:
    """How long ago `local_time` was, in plain words (e.g. '3 minutes ago')."""
    seconds = max(
        0.0,
        (pd.Timestamp.now(tz=local_time.tzinfo) - local_time).total_seconds(),
    )
    for unit, size in (("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = round(seconds / size)
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    count = round(seconds)
    return f"{count} second{'s' if count != 1 else ''} ago"


def render() -> None:
    engines = engine_databases(st.session_state.root)
    if not engines:
        st.warning(
            f"No engine has recorded anything under "
            f"`{st.session_state.root}` yet."
        )
        return

    errors = error_rows(engines)
    if errors.empty:
        st.info("No ERROR logs recorded yet.")
        return

    page, show_pagination = paginate(
        errors, key="error-log", page_size=PAGE_SIZE
    )
    page = page.assign(
        local_time=_local_time(page["created"].astype(float)),
        clean_message=page["msg"].map(_clean_message),
    )

    row_levels: list[tuple[str, str]] = []
    for _, row in page.iterrows():
        level = row.get("levelname", "ERROR")
        # `created` uniquely identifies a log record within one engine's
        # log, and two engines can log in the same instant - so an entry
        # already shown keeps its key (and its mounted DOM node) across
        # reruns even as newer entries push it down the list.
        key = row_key("error", f"{row['engine_key']} {row['created']}")
        row_levels.append((key, level))
        summary = (
            f"`{row['engine_label']}`  ·  {_relative_age(row['local_time'])}"
            f"  ·  {row['clean_message']}"
        )
        with st.container(key=key):
            with st.expander(
                summary, icon=_LEVEL_ICONS.get(level, ":material/error:")
            ):
                st.caption(
                    f"{row['engine_label']} · {row.get('name', '-')} · "
                    f"{row.get('filename', '-')}:{row.get('lineno', '-')}"
                )
                if row["clean_message"] != row["msg"]:
                    st.code(row["msg"], language=None)

    show_pagination()

    accent_rules = "\n".join(
        f".st-key-{key} {{ border-left: 3px solid "
        f"{_LEVEL_ACCENTS.get(level, SEMANTIC_COLORS['gray'])};"
        f" padding-left: 8px; }}"
        for key, level in row_levels
    )
    st.html(f"<style>{accent_rules}{_SQUARE_ROW_CSS}</style>")
