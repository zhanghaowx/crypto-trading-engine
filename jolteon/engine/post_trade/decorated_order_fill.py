from dataclasses import dataclass
from datetime import datetime

from jolteon.engine.core.side import MarketSide


@dataclass(frozen=True)
class DecoratedOrderFill:
    """Immutable execution facts used by post-trade analytics.

    Fair value and markouts are deliberately not stored here. They are
    derived later from this fill and the recorded fair-price series, so a
    recording can be analyzed at arbitrary horizons without scheduling
    callbacks while the engine is running.
    """

    PRIMARY_KEY = "unique_trade_id"

    unique_trade_id: str
    client_order_id: str
    exchange: str
    exchange_order_id: str
    exchange_execution_id: str
    transaction_timestamp: datetime
    symbol: str
    side: MarketSide
    fill_price: float
    fill_qty: float
    fee: float
    fair_price_model: str
