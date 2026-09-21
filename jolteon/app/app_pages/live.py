import streamlit as st

from jolteon.app.app_pages import (
    fair_price_signals,
    order_book,
    orders_pnl,
    risk_limits,
)
from jolteon.app.card import Card, cards_rule, render_cards
from jolteon.app.data import engine_databases, latest_engine_run
from jolteon.app.health_summary import watch_nav
from jolteon.app.settings import ENGINE, refresh_interval


def _render_run_scope() -> None:
    run = latest_engine_run(st.session_state.db_path)
    if run is None:
        return
    short_id = run.run_id.rsplit("-", 1)[-1]
    label = {
        "running": "Running",
        "stopped": "Stopped",
        "interrupted": "Interrupted",
    }[run.status]
    st.caption(
        f"Run `{short_id}` · started "
        f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC · {label}"
    )


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

# Outside the cards' own fragments: they read whichever engine this
# picks, so it has to be settled before any of them run, and choosing
# another engine is meant to invalidate every one of them at once.
_select_engine()
_render_run_scope()

# Each card refreshes itself on a timer of its own (see `card.card`), so
# there is no page-wide fragment here to redraw the lot.
render_cards(cards)
watch_nav(refresh_interval())
