import streamlit as st

from jolteon.app.app_pages import (
    fair_price_signals,
    health,
    logs,
    market_data,
    orders_pnl,
    risk_limits,
)
from jolteon.app.components import (
    Section,
    render_sections,
    section_surface_rule,
)
from jolteon.app.data import engine_databases
from jolteon.app.settings import use_engine

_ENGINE_KEY = "live-engine-symbol"


def _select_engine() -> None:
    """
    Which engine's recording the sections below read.

    One engine trades one symbol and records to its own file, so choosing
    a symbol is choosing a database. Nothing is offered while only one
    engine has been running, since there is nothing to choose between.
    """
    engines = engine_databases(st.session_state.root)
    if len(engines) < 2:
        return

    by_symbol = {engine.symbol: engine for engine in engines}
    symbol = st.segmented_control(
        "Symbol",
        options=list(by_symbol),
        default=next(iter(by_symbol)),
        key=_ENGINE_KEY,
        label_visibility="collapsed",
    )
    # A segmented control lets the reader clear their own selection.
    if symbol in by_symbol:
        use_engine(by_symbol[symbol])


sections: list[Section] = [
    # Health leads: if a component has gone quiet, everything below it
    # is stale data and the reader needs to know that first.
    ("Health", ":material/monitor_heart:", health.render, None, None),
    (
        "Market Data",
        ":material/show_chart:",
        market_data.render,
        None,
        None,
    ),
    (
        "Risk Limits",
        ":material/earthquake:",
        risk_limits.render,
        None,
        None,
    ),
    (
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
        orders_pnl.render_header_actions,
        None,
    ),
    (
        "Trade Quality",
        ":material/target:",
        orders_pnl.render_trade_quality,
        None,
        None,
    ),
    (
        "Fair Price Signals",
        ":material/insights:",
        fair_price_signals.render,
        None,
        None,
    ),
    (
        "Errors",
        ":material/error:",
        logs.render,
        None,
        logs.has_errors,
    ),
]

st.html(section_surface_rule(title for title, *_ in sections))

# Outside the refreshing fragment: the sections below read whichever
# engine this picks, so it has to be settled before they run, and a
# selector redrawn on every refresh would fight the reader for it.
_select_engine()

# `run_every` reruns just this fragment on a timer without blocking the
# session - the previous `time.sleep` + `st.rerun()` loop did block it,
# which let a periodic refresh race with a widget interaction inside it
# (e.g. paging through Recent fills): the two reruns' element streams
# could interleave and leave stale rows behind. Re-applying the
# decorator every run picks up live changes to the auto-refresh setting.
_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)
st.fragment(render_sections, run_every=_refresh_seconds)(sections)
