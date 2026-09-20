import streamlit as st

from jolteon.app.app_pages import (
    fair_price_signals,
    order_book,
    orders_pnl,
    risk_limits,
)
from jolteon.app.card import Card, cards_rule, render_cards
from jolteon.app.data import engine_databases
from jolteon.app.health_summary import redraw_nav_if_stale
from jolteon.app.settings import ENGINE


def _select_engine() -> None:
    """
    Which engine's recording the cards below read.

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
        # every card below would go on showing the engine the reader
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


cards = [
    Card(
        "Order Book",
        ":material/bar_chart:",
        order_book.render,
        width="half",
    ),
    Card(
        "Risk Limits",
        ":material/earthquake:",
        risk_limits.render,
        accent=risk_limits.accent,
        width="half",
    ),
    Card(
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
        actions=orders_pnl.render_header_actions,
        accent=orders_pnl.accent,
    ),
    Card(
        "Trade Quality", ":material/target:", orders_pnl.render_trade_quality
    ),
    Card(
        "Fair Price Signals",
        ":material/insights:",
        fair_price_signals.render,
        details=fair_price_signals.render_details,
    ),
]

st.html(cards_rule(cards))

# Outside the refreshing fragment: the cards below read whichever
# engine this picks, so it has to be settled before they run, and a
# selector redrawn on every refresh would fight the reader for it.
_select_engine()

# `run_every` reruns just this fragment on a timer without blocking the
# session. One fragment for the whole page rather than one per card:
# each fragment costs its own round trip and its own pass over the
# frontend, and five of them staggered leave the app looking busy more
# than twice as much of the time as one that redraws the lot at once.
# Re-applying the decorator every run picks up live changes to the
# auto-refresh setting.
_refresh_seconds = (
    st.session_state.refresh_seconds if st.session_state.auto_refresh else None
)


def _refresh(cards: list[Card]) -> None:
    render_cards(cards)
    redraw_nav_if_stale(st.session_state.root)


st.fragment(_refresh, run_every=_refresh_seconds)(cards)
