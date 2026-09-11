import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.app.components import (
    paginate,
    row_add_rule,
    row_key,
    warn_if_no_db,
)
from jolteon.app.data import as_datetime, read_table

PAGE_SIZE = 10

# CRITICAL is the same kind of thing an operator calls an "error" as ERROR
# is - just a more severe one - so both belong in this card. Everything
# below ERROR (INFO, WARNING) is recorded (see setup_global_logger) but
# deliberately never shown here.
_LEVELS = ("ERROR", "CRITICAL")

_LEVEL_ICONS: dict[str, str] = {
    "ERROR": ":material/error:",
    "CRITICAL": ":material/dangerous:",
}

# The same colors HEARTBEAT_BADGES uses for these levels (config.toml).
_LEVEL_ACCENTS: dict[str, str] = {
    "ERROR": "#E8873C",
    "CRITICAL": "#DC2626",
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


def _read_errors(log_db_path: str) -> pd.DataFrame:
    logs = read_table(log_db_path, "logs")
    return (
        logs[logs["levelname"].isin(_LEVELS)]
        if "levelname" in logs.columns
        else logs.iloc[0:0]
    )


def has_errors() -> bool:
    """Whether the Errors card has anything to show. "No errors" is a
    non-event on a live trading dashboard, not worth a card of its own,
    so the card is skipped once there's a log database to confirm that -
    but not before: while the database doesn't exist yet, every other
    section still shows its own "waiting for the engine" warning, and
    this one should too rather than silently vanishing."""
    log_db_path = st.session_state.log_db_path
    if not Path(log_db_path).exists():
        return True
    return not _read_errors(log_db_path).empty


def render() -> None:
    log_db_path = st.session_state.log_db_path
    if not warn_if_no_db(log_db_path):
        return

    errors = _read_errors(log_db_path)
    if errors.empty:
        st.info("No ERROR logs recorded yet.")
        return

    errors = errors.sort_values("created", ascending=False)
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
        # `created` uniquely identifies the underlying log record, so an
        # entry already shown keeps its key (and its mounted DOM node)
        # across reruns even as newer entries push it down the list.
        key = row_key("error", str(row["created"]))
        row_levels.append((key, level))
        summary = (
            f"{_relative_age(row['local_time'])}  ·  {row['clean_message']}"
        )
        with st.container(key=key):
            with st.expander(
                summary, icon=_LEVEL_ICONS.get(level, ":material/error:")
            ):
                st.caption(
                    f"{row.get('name', '-')} · "
                    f"{row.get('filename', '-')}:{row.get('lineno', '-')}"
                )
                if row["clean_message"] != row["msg"]:
                    st.code(row["msg"], language=None)

    show_pagination()

    accent_rules = "\n".join(
        f".st-key-{key} {{ border-left: 3px solid "
        f"{_LEVEL_ACCENTS.get(level, '#8A8D91')}; padding-left: 8px; }}"
        for key, level in row_levels
    )
    st.html(
        f"<style>{row_add_rule('error')}{accent_rules}{_SQUARE_ROW_CSS}"
        f"</style>"
    )
