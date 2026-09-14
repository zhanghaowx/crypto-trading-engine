import streamlit as st

from jolteon.app.app_pages import (
    fair_price_signals,
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
from jolteon.app.health_summary import redraw_nav_if_stale
from jolteon.app.settings import ENGINE


def _select_engine() -> None:
    """
    Which engine's recording the sections below read.

    One engine trades one symbol and records to its own file, so choosing
    a symbol is choosing a database - which `init_settings` resolves from
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
        # every section below would go on showing the engine the reader
        # had just stopped asking for.
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


sections: list[Section] = [
    ("Market Data", ":material/show_chart:", market_data.render, None),
    ("Risk Limits", ":material/earthquake:", risk_limits.render, None),
    (
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
        orders_pnl.render_header_actions,
    ),
    (
        "Trade Quality",
        ":material/target:",
        orders_pnl.render_trade_quality,
        None,
    ),
    (
        "Fair Price Signals",
        ":material/insights:",
        fair_price_signals.render,
        None,
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


def _refresh(sections: list[Section]) -> None:
    render_sections(sections)
    redraw_nav_if_stale(st.session_state.root)


st.fragment(_refresh, run_every=_refresh_seconds)(sections)
