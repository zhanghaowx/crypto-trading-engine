from dataclasses import dataclass
from datetime import datetime

from jolteon.core.side import MarketSide


@dataclass(frozen=True, order=True)
class Trade:
    trade_id: int
    client_order_id: str
    symbol: str
    maker_order_id: str
    taker_order_id: str
    side: MarketSide
    price: float
    fee: float
    quantity: float
    transaction_time: datetime
