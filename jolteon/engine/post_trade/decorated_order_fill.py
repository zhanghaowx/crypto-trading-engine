from dataclasses import dataclass
from datetime import datetime

from jolteon.engine.core.side import MarketSide


@dataclass
class DecoratedOrderFill:
    PRIMARY_KEY = "unique_trade_id"

    unique_trade_id: str
    session_id: str
    client_order_id: str
    exchange: str
    exchange_order_id: str
    exchange_execution_id: str
    transaction_timestamp: datetime
    symbol: str
    side: MarketSide
    fill_price: float
    fill_qty: float
    fair_price_at_fill: float
    fee: float
    fair_price_100ms: float | None = None
    fair_price_1s: float | None = None
    fair_price_5s: float | None = None
    fair_price_30s: float | None = None
