from dataclasses import dataclass


@dataclass
class BBO:
    """
    Best Bid and Offer of the current market
    """

    EXTERNAL_EVENT = True

    symbol: str
    bid_price: float
    bid_quantity: float
    ask_price: float
    ask_quantity: float
