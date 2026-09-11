from jolteon.engine.market_data.core.order_book import PriceLevel


def imbalance(bids: list[PriceLevel], asks: list[PriceLevel]) -> float:
    """
    Returns: How lopsided the resting size is across the levels given,
    from -1.0 (all size on the ask) to 1.0 (all size on the bid), and 0.0
    when there is nothing resting. How deep to look is the caller's
    choice, expressed in the levels it passes.
    """
    bid_quantity = sum(level.quantity for level in bids)
    ask_quantity = sum(level.quantity for level in asks)
    total_quantity = bid_quantity + ask_quantity

    if total_quantity <= 0:
        return 0.0

    return (bid_quantity - ask_quantity) / total_quantity


def vwap(levels: list[PriceLevel], quantity: float) -> float | None:
    """
    Returns: The average price of filling `quantity` against the levels
    given, best price first, or None when they do not hold enough size to
    fill it.
    """
    if quantity <= 0:
        return None

    remaining = quantity
    notional = 0.0
    for level in levels:
        taken = min(remaining, level.quantity)
        notional += taken * level.price
        remaining -= taken
        if remaining <= 0:
            return notional / quantity

    return None
