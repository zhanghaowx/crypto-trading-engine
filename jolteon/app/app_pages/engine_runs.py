"""The engine runs a trading session was traded by.

A trading session is what strategy performance is measured over, and a
run is one process lifetime. The two are told apart precisely so a
restart cannot split a day's figures - but a restart is still what a gap
in the day's market data, or an order the engine lost track of, should
be blamed on before the strategy is. That is what this shows.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app import aggregates, settings, table
from jolteon.app.data import as_datetime, engine_databases
from jolteon.app.health_summary import is_down

_STOPPED = "Stopped"
_RUNNING = "Running"
_INTERRUPTED = "Ended without stopping"


def _local(seconds: float) -> str:
    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    return (
        as_datetime(pd.Series([seconds]))[0]
        .tz_convert(local_tz)
        .strftime("%H:%M:%S")
    )


def _outcome(run) -> str:
    """How a run left the session.

    A run records its own end as it shuts down, so one with no end
    recorded either never got the chance or has not reached it yet -
    told apart by whether it is still recording.
    """
    if not pd.isna(run.ended_at):
        return _STOPPED
    quiet_for = pd.Timestamp.now(tz="UTC").timestamp() - run.last_seen_at
    return _INTERRUPTED if is_down(quiet_for) else _RUNNING


def runs_table(runs: pd.DataFrame) -> pd.DataFrame:
    """`runs` in the terms a reader diagnosing a restart needs: when each
    process was trading this session, and how it left it."""
    return pd.DataFrame(
        {
            "Run": [str(run.run_id) for run in runs.itertuples()],
            "From": [_local(run.first_seen_at) for run in runs.itertuples()],
            "To": [_local(run.last_seen_at) for run in runs.itertuples()],
            "Outcome": [_outcome(run) for run in runs.itertuples()],
        }
    )


def render() -> None:
    engines = engine_databases(st.session_state.root)
    if not engines:
        st.warning(
            f"No engine has recorded anything under "
            f"`{st.session_state.root}` yet."
        )
        return

    session_id = settings.session_id()
    if session_id is None:
        st.info("No trading session recorded yet.")
        return

    for engine in engines:
        if len(engines) > 1:
            st.markdown(f"**{engine.label}**")
        runs = aggregates.engine_runs(engine.path, session_id)
        if runs.empty:
            st.info(f"Nothing recorded in {session_id}.")
            continue
        table.render(
            runs_table(runs),
            column_help={
                "Run": (
                    "One engine process, from start to stop. Several may "
                    "trade one session; the session's own figures add up "
                    "across them."
                ),
                "Outcome": (
                    f'"{_INTERRUPTED}" means the process never recorded '
                    f"its own end, so it was killed rather than shut down."
                ),
            },
        )
