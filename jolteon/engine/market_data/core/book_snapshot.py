from dataclasses import dataclass

from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order_book import PriceLevel


@dataclass(frozen=True)
class BookSnapshot:
    """
    One symbol's book as it stood at a single moment. The published order
    book keeps changing after that, so its levels are copied in here
    rather than referenced.

    `bids` and `asks` run best price first, and are empty when no depth
    is available.
    """

    bbo: BBO
    bids: tuple[PriceLevel, ...] = ()
    asks: tuple[PriceLevel, ...] = ()
