"""What a card is: its identity, its callbacks, and what it costs to draw.

Nothing here draws anything. A page declares its cards with these and
hands them to `render_cards`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal

from jolteon.dashboard.ui.primitives import BadgeColor

Accent = BadgeColor | None

CardWidth = Literal["full", "half"]


@dataclass(frozen=True)
class Card:
    """One titled card on a page, and what goes inside it.

    `id` is what the card is known by everywhere a name has to outlive
    the words on screen: its container key, whether the reader has hidden
    it, whether its details are open. The title is what the card is
    called on the page and nothing else, so it can be reworded without
    the reader's own choices about the card falling on the floor.

    `actions` draws controls of the card's own onto the title row,
    alongside the collapse, details and hide icons every card carries.
    `details` is what the card has to say beyond what it shows in
    place. Give it and the card carries a "more" icon that opens it in a
    modal; leave it out and the card carries no such icon.

    `accent` stripes the card's left edge. A card whose color says
    something that changes - a limit going from comfortable to nearly
    breached - gives a function instead of a color, which is called each
    time the card is drawn.

    `width` is how much of the page's own width a card asks for. Half
    cards pair up with the next half card on the page, so two of them
    share a row.

    `refresh` and `refresh_interval` are the card's own refresh policy:
    whether it redraws itself on a timer at all, and how often if the
    dashboard-wide interval is not what it wants. The page it sits on
    has no say in either.

    With `load`, each execution loads one model and passes it to body,
    actions, details, and callable accent. Without it, callbacks take no
    arguments. `manual_refresh` controls the independent refresh button.
    """

    id: str
    title: str
    icon: str
    body: Callable[..., None]
    actions: Callable[..., None] | None = None
    details: Callable[..., None] | None = None
    accent: Accent | Callable[..., Accent] = None
    width: CardWidth = "full"
    refresh: bool = True
    refresh_interval: float | None = None
    manual_refresh: bool = True
    load: Callable[[], Any] | None = None


def card_key(card_id: str) -> str:
    return f"card-{card_id}"


@dataclass
class CardMetrics:
    """Session-local timings; load time includes any source cache lookup."""

    refresh_count: int = 0
    last_refresh_at: datetime | None = None
    load_ms: float = 0.0
    render_ms: float = 0.0
    total_ms: float = 0.0
    error_count: int = 0
