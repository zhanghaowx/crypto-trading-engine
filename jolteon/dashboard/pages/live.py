import streamlit as st

from jolteon.dashboard.cards import (
    fair_price_signals,
    order_book,
    orders_pnl,
    risk_limits,
    trade_quality,
)
from jolteon.dashboard.state import current_run, refresh_interval
from jolteon.dashboard.ui.cards import Card, cards_rule, render_cards
from jolteon.dashboard.ui.engine_selection import (
    run_mode,
    run_status,
    select_engine,
)
from jolteon.dashboard.ui.navigation import watch_nav


def _render_run_scope() -> None:
    run = current_run()
    if run is None:
        return
    short_id = run.run_id.rsplit("-", 1)[-1]
    st.caption(
        f"Run `{short_id}` · started "
        f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC · {run_status(run)} · "
        f"{run_mode(run)}"
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
        trade_quality.render,
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
select_engine()
_render_run_scope()

# Each card refreshes itself on a timer of its own (see `card.card`), so
# there is no page-wide fragment here to redraw the lot.
render_cards(cards)
watch_nav(refresh_interval())
