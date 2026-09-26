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
from jolteon.dashboard.ui.engine_selection import select_engine
from jolteon.dashboard.ui.navigation import watch_nav
from jolteon.dashboard.ui.page_header import context_bar

cards = [
    # The session's figures lead, as a row of the page rather than a card
    # on it; the cards under them are what those figures are made of.
    Card(
        "summary",
        "Summary",
        ":material/summarize:",
        orders_pnl.render_summary,
        load=orders_pnl.load,
        frame="bare",
    ),
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
        "recent-fills",
        "Recent fills",
        ":material/receipt_long:",
        orders_pnl.render,
        load=orders_pnl.load,
        actions=orders_pnl.render_header_actions,
    ),
    Card(
        "trade-quality",
        "Trade quality",
        ":material/target:",
        trade_quality.render,
    ),
]

st.html(cards_rule(cards))

# Outside the cards' own fragments: they read whichever engine this
# picks, so it has to be settled before any of them run, and choosing
# another engine is meant to invalidate every one of them at once.
with context_bar(current_run(), live=True):
    select_engine()

# Each card refreshes itself on a timer of its own (see `card.card`), so
# there is no page-wide fragment here to redraw the lot.
render_cards(cards)
watch_nav(refresh_interval())
