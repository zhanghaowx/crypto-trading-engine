import re
from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import row_add_rule, row_key, warn_if_no_db
from jolteon.app.data import as_datetime, read_table

MAX_ROWS = 20

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


def render() -> None:
    log_db_path = st.session_state.log_db_path
    if not warn_if_no_db(log_db_path):
        return

    logs = read_table(log_db_path, "logs")
    errors = (
        logs[logs["levelname"] == "ERROR"]
        if "levelname" in logs.columns
        else logs.iloc[0:0]
    )
    if errors.empty:
        st.info("No ERROR logs recorded yet.")
        return

    recent = errors.sort_values("created", ascending=False).head(MAX_ROWS)
    recent = recent.assign(
        local_time=_local_time(recent["created"].astype(float)),
        clean_message=recent["msg"].map(_clean_message),
    )

    for _, row in recent.iterrows():
        summary = f"{row['local_time']:%H:%M:%S}  ·  {row['clean_message']}"
        # `created` uniquely identifies the underlying log record, so an
        # entry already shown keeps its key (and its mounted DOM node)
        # across reruns even as newer entries push it down the list.
        with st.container(key=row_key("error", str(row["created"]))):
            with st.expander(summary, icon=":material/error:"):
                st.caption(
                    f"{row.get('name', '-')} · "
                    f"{row.get('filename', '-')}:{row.get('lineno', '-')}"
                )
                if row["clean_message"] != row["msg"]:
                    st.code(row["msg"], language=None)
    st.html(f"<style>{row_add_rule('error')}</style>")
