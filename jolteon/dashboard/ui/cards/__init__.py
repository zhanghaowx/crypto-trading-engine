"""The dashboard's card: a bordered surface with a title and its own chrome.

Every page is built out of these. A page declares `Card`s and hands them
to `render_cards`; the look of one, the controls on it and the way a
group of them lays out are settled here rather than in each page.
"""

from jolteon.dashboard.ui.cards.layout import card_grid, render_cards
from jolteon.dashboard.ui.cards.model import (
    Accent,
    Card,
    CardFrame,
    CardMetrics,
    CardWidth,
    card_key,
)
from jolteon.dashboard.ui.cards.runtime import card, refresh_every
from jolteon.dashboard.ui.cards.style import cards_rule, surface_rule

__all__ = [
    "Accent",
    "Card",
    "CardFrame",
    "CardMetrics",
    "CardWidth",
    "card",
    "card_grid",
    "card_key",
    "cards_rule",
    "refresh_every",
    "render_cards",
    "surface_rule",
]
