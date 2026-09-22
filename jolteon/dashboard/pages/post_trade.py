import streamlit as st

from jolteon.dashboard.card import Card, cards_rule, render_cards
from jolteon.dashboard.components import run_status, select_engine
from jolteon.dashboard.health_summary import resolve_runs
from jolteon.dashboard.pages import session_economics

ANALYSIS_RUN = "analysis_run_id"


def _select_run() -> str | None:
    """
    Which finished run everything below is measured over.

    The reader's own choice out of the runs that have ended, newest
    first. The run happening now is left out: this page draws once and
    does not refresh, so a run whose figures are still moving would be
    read here as though it were final - and that run is what the Live
    page is for. A run the engine died in is finished too, and belongs
    here as much as one that stopped cleanly.
    """
    db_path = st.session_state.db_path
    recorded = resolve_runs(db_path)
    if not recorded:
        st.info("No engine runs have been recorded yet.")
        return None

    runs = [run for run in recorded if run.status != "running"]
    if not runs:
        st.info(
            "The engine's only run so far is still going. Watch it on the "
            "Live page; this page reads runs that have ended."
        )
        return None

    options = [run.run_id for run in runs]
    # A run chosen under one engine is not a run under the next one, and a
    # selectbox handed a remembered value that is not on offer raises.
    if st.session_state.get(ANALYSIS_RUN) not in options:
        st.session_state.pop(ANALYSIS_RUN, None)

    by_id = {run.run_id: run for run in runs}

    def label(run_id: str) -> str:
        run = by_id[run_id]
        short_id = run_id.rsplit("-", 1)[-1]
        return (
            f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC · "
            f"{short_id} · {run_status(run)}"
        )

    return st.selectbox(
        "Engine run",
        options=options,
        format_func=label,
        key=ANALYSIS_RUN,
    )


select_engine()
run_id = _select_run()

if run_id is not None:
    cards = [
        Card(
            "session-economics",
            "Session Economics",
            ":material/payments:",
            session_economics.render,
            load=lambda: session_economics.load(
                st.session_state.db_path, run_id
            ),
            details=session_economics.render_details,
            # A finished run's figures do not move, and the run happening
            # now is what the Live page is for.
            refresh=False,
        )
    ]
    st.html(cards_rule(cards))
    render_cards(cards)
