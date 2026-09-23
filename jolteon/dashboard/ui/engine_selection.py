"""Which engine a page reads, and what its run is doing.

One engine trades one symbol into a recording of its own, so the page
header offers the symbol and says whether the run behind it is still
going.
"""

import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.state import ENGINE
from jolteon.engine.core.engine_run import ExecutionMode, MarketDataMode


def select_engine() -> None:
    """
    Which engine's recording the page below reads.

    One engine trades one symbol and records to its own file, so choosing
    a symbol is choosing a database - which `init_state` resolves from
    the choice this leaves behind. Nothing is offered while only one
    engine has been running, since there is nothing to choose between.
    """
    engines = engine_databases(st.session_state.root)
    if len(engines) < 2:
        return

    st.segmented_control(
        "Symbol",
        options=[engine.key for engine in engines],
        default=engines[0].key,
        format_func=lambda key: next(
            engine.label for engine in engines if engine.key == key
        ),
        # A page that reads one engine has to be reading one: cleared,
        # everything below would go on showing the engine the reader had
        # just stopped asking for.
        required=True,
        key=ENGINE,
        # The binding carries the symbol in the URL, so a link names the
        # symbol it was copied from. `persist_state` is what carries it
        # across a page switch: a bound value belongs to the page that
        # bound it, and is dropped from the URL on the way to another.
        bind="query-params",
        persist_state="session",
        label_visibility="collapsed",
    )


# What a run's status is called on screen. The recording's own "open" is
# settled into one of these by `services.health.resolve_run`.
_RUN_STATUS_LABELS = {
    "running": "Running",
    "stopped": "Stopped",
    "interrupted": "Interrupted",
}


def run_status(run: RecordedEngineRun) -> str:
    """A run's status in the words a reader sees, the same on every page."""
    return _RUN_STATUS_LABELS[run.status]


# How a run executed and where its market data came from, in the words a
# reader uses for the pair. "Paper trading" is what a simulated run off a
# live feed is called; a simulated run off a recording is a replay, and
# calling that paper trading too would hide which of the two is on
# screen.
# Keyed by the recorded text rather than by the enum, which is what a
# recording holds and what an older recording holds none of.
_RUN_MODE_LABELS: dict[tuple[str, str], str] = {
    (ExecutionMode.SIMULATED, MarketDataMode.REALTIME): "Paper · Live feed",
    (ExecutionMode.SIMULATED, MarketDataMode.RECORDED): "Simulation · Replay",
    (ExecutionMode.REAL, MarketDataMode.REALTIME): "Live · Live feed",
    (ExecutionMode.REAL, MarketDataMode.RECORDED): "Live · Replay",
}

UNRECORDED_MODE = "Mode not recorded"


def run_mode(run: RecordedEngineRun) -> str:
    """How a run executed and where its data came from, said as one
    phrase - and said to be unknown for a run recorded before an engine
    wrote either down."""
    return _RUN_MODE_LABELS.get(
        (run.execution_mode, run.market_data_mode), UNRECORDED_MODE
    )
