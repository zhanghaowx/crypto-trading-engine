from dataclasses import dataclass
from datetime import datetime

from crypto_trading_engine.core.side import MarketSide


@dataclass(frozen=True, order=True)
class Trade:
    PRIMARY_KEY = "trade_id"
    trade_id: int
    sequence_number: int
    symbol: str
    maker_order_id: str
    taker_order_id: str
    side: MarketSide
    price: float
    quantity: float
    transaction_time: datetime
