import streamlit as st

from jolteon.dashboard.cards import session_economics
from jolteon.dashboard.data.runs import RecordedEngineRun
from jolteon.dashboard.services.health import resolve_runs
from jolteon.dashboard.ui.cards import Card, cards_rule, render_cards
from jolteon.dashboard.ui.engine_selection import replay_source, select_engine
from jolteon.dashboard.ui.page_header import context_bar

ANALYSIS_RUN = "analysis_run_id"


def _chosen(runs: list[RecordedEngineRun]) -> RecordedEngineRun:
    """
    The finished run everything below is measured over: the reader's own
    choice, else the newest.

    Settled before the picker is drawn, so the bar the picker sits in can
    describe the run it shows. A run chosen under one engine is not a run
    under the next one, and a selectbox handed a remembered value that is
    not on offer raises.
    """
    by_id = {run.run_id: run for run in runs}
    chosen = st.session_state.get(ANALYSIS_RUN)
    if chosen not in by_id:
        st.session_state.pop(ANALYSIS_RUN, None)
        return runs[0]
    return by_id[chosen]


def _select_run(runs: list[RecordedEngineRun]) -> None:
    """The finished runs on offer, newest first, each named by when it
    started and what it was called - its status and modes are the bar's
    badges."""

    def label(run_id: str) -> str:
        run = next(run for run in runs if run.run_id == run_id)
        short_id = run_id.rsplit("-", 1)[-1]
        return f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC · {short_id}"

    st.selectbox(
        "Engine run",
        options=[run.run_id for run in runs],
        format_func=label,
        key=ANALYSIS_RUN,
        label_visibility="collapsed",
        width=300,
    )


db_path = st.session_state.db_path
recorded = resolve_runs(db_path)
# The run happening now is left out: this page draws once and does not
# refresh, so a run whose figures are still moving would be read here as
# though it were final - and that run is what the Live page is for. A run
# the engine died in is finished too, and belongs here as much as one
# that stopped cleanly.
runs = [run for run in recorded if run.status != "running"]
run = _chosen(runs) if runs else None

with context_bar(run):
    select_engine()
    if runs:
        _select_run(runs)

if not recorded:
    st.info("No engine runs have been recorded yet.")
elif run is None:
    st.info(
        "The engine's only run so far is still going. Watch it on the "
        "Live page; this page reads runs that have ended."
    )
else:
    # Only a replay has one, and only there does the reader need to know
    # which recording the figures below were produced from.
    source = replay_source(run)
    if source:
        st.caption(source)

    run_id = run.run_id

    def load() -> session_economics.SessionEconomicsModel:
        return session_economics.load(db_path, run_id)

    cards = [
        # A finished run's figures do not move, and the run happening now
        # is what the Live page is for - so nothing here refreshes.
        Card(
            "summary-session",
            "Summary",
            ":material/summarize:",
            session_economics.render_summary,
            load=load,
            refresh=False,
            frame="bare",
        ),
        Card(
            "execution-economics",
            "Execution economics",
            ":material/payments:",
            session_economics.render,
            load=load,
            details=session_economics.render_details,
            refresh=False,
        ),
    ]
    st.html(cards_rule(cards))
    render_cards(cards)
