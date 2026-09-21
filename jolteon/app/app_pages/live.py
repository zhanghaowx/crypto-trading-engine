import streamlit as st

from jolteon.app import aggregates
from jolteon.app.app_pages import (
    fair_price_signals,
    order_book,
    orders_pnl,
    risk_limits,
)
from jolteon.app.card import Card, cards_rule, render_cards
from jolteon.app.data import engine_databases
from jolteon.app.health_summary import watch_nav
from jolteon.app.settings import ENGINE, SESSION, refresh_interval


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


def _select_session() -> None:
    """
    Which trading session the cards below report on.

    A recording goes on accumulating across restarts and across days, so
    the figures on screen have to say which day they are of. The newest
    is offered first and is what a reader who picks nothing gets.
    Nothing is offered while the recording holds only one session, since
    there is nothing to choose between.
    """
    recorded = aggregates.sessions(st.session_state.db_path)
    if len(recorded) < 2:
        return
    options = [str(one) for one in recorded["session_id"]]

    # Another engine's recording may hold none of the days this one did,
    # and a picker cannot be built around a value its options lack.
    if st.session_state.get(SESSION) not in options:
        st.session_state.pop(SESSION, None)

    st.selectbox(
        "Trading session",
        options=options,
        key=SESSION,
        # A day is eight characters wide; left to fill the page the
        # picker reads as a banner rather than as one small choice.
        width=220,
        # The binding carries the day in the URL, so a link names the
        # session it was copied from, and `persist_state` is what keeps
        # it through a switch to another page and back.
        bind="query-params",
        persist_state="session",
        help=(
            "Which UTC day the figures below cover. Inventory and orders "
            "carry across midnight; only the accounting starts again."
        ),
    )


cards = [
    Card(
        "order-book",
        "Order Book",
        ":material/bar_chart:",
        order_book.render,
        width="half",
    ),
    Card(
        "risk-limits",
        "Risk Limits",
        ":material/earthquake:",
        risk_limits.render,
        accent=risk_limits.accent,
        width="half",
    ),
    Card(
        "orders-pnl",
        "Orders & PnL",
        ":material/currency_bitcoin:",
        orders_pnl.render,
        load=orders_pnl.load,
        actions=orders_pnl.render_header_actions,
        accent=orders_pnl.accent,
    ),
    Card(
        "trade-quality",
        "Trade Quality",
        ":material/target:",
        orders_pnl.render_trade_quality,
    ),
    Card(
        "fair-price-signals",
        "Fair Price Signals",
        ":material/insights:",
        fair_price_signals.render,
        details=fair_price_signals.render_details,
    ),
]

st.html(cards_rule(cards))

# Outside the cards' own fragments: they read whichever engine and
# whichever session these pick, so both have to be settled before any of
# them run, and choosing again is meant to invalidate every one at once.
_select_engine()
_select_session()

# Each card refreshes itself on a timer of its own (see `card.card`), so
# there is no page-wide fragment here to redraw the lot.
render_cards(cards)
watch_nav(refresh_interval())
