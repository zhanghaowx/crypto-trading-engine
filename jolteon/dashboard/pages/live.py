import streamlit as st

from jolteon.dashboard.cards import (
    fair_price_signals,
    order_book,
    orders_pnl,
    risk_limits,
    session_performance,
    trade_quality,
)
from jolteon.dashboard.state import current_run, refresh_interval
from jolteon.dashboard.ui.cards import Card, cards_rule, render_cards
from jolteon.dashboard.ui.engine_selection import select_engine
from jolteon.dashboard.ui.navigation import watch_nav
from jolteon.dashboard.ui.page_header import page_heading, run_scope_caption

overview_cards = [
    Card(
        "order-book",
        "Order book",
        ":material/bar_chart:",
        order_book.render,
        width="half",
    ),
    Card(
        "risk-limits",
        "Risk limits",
        ":material/earthquake:",
        risk_limits.render,
        accent=risk_limits.accent,
        width="half",
    ),
    Card(
        "fair-price-signals",
        "Fair price signals",
        ":material/insights:",
        fair_price_signals.render,
        details=fair_price_signals.render_details,
    ),
    Card(
        "session-performance",
        "Session performance",
        ":material/show_chart:",
        session_performance.render,
        load=session_performance.load,
    ),
]

fills_cards = [
    Card(
        "recent-fills",
        "Recent fills",
        ":material/receipt_long:",
        orders_pnl.render_fills,
        load=orders_pnl.load,
        actions=orders_pnl.render_header_actions,
    ),
]

quality_cards = [
    Card(
        "trade-quality",
        "Trade quality",
        ":material/target:",
        trade_quality.render,
    ),
]

st.html(cards_rule(overview_cards + fills_cards + quality_cards))

page_heading("Live", "What this engine is doing right now.")

# Outside the cards' own fragments: they read whichever engine this
# picks, so it has to be settled before any of them run, and choosing
# another engine is meant to invalidate every one of them at once.
select_engine()
run_scope_caption(current_run())

# The KPI row carries no card chrome of its own - it is the prototype's
# `.kpis` strip, sitting directly under the scope bar - so it is kept out
# of `render_cards` and given a bare fragment instead, just to keep its
# own refresh timer independent of the rest of the page.
st.fragment(orders_pnl.render_kpis, run_every=refresh_interval())()

overview_tab, fills_tab, quality_tab = st.tabs(
    ["Overview", "Fills", "Execution quality"]
)
with overview_tab:
    render_cards(overview_cards)
with fills_tab:
    render_cards(fills_cards)
with quality_tab:
    render_cards(quality_cards)

watch_nav(refresh_interval())
