from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Union

from jolteon.core.side import MarketSide


class OrderType(StrEnum):
    MARKET_ORDER = "market"
    LIMIT_ORDER = "limit"
    STOP_LOSS_ORDER = "stop-loss"
    TAKE_PROFIT_ORDER = "take-profit"
    STOP_LOSS_LIMIT_ORDER = "stop-loss-limit"
    TAKE_PROFIT_LIMIT_ORDER = "take-profit-limit"
    TRAILING_STOP_ORDER = "trailing-stop"
    TRAILING_STOP_LIMIT_ORDER = "trailing-stop-limit"
    SETTLE_POSITION_ORDER = "settle-position"


@dataclass
class Order:
    """
    Represents an order placed in the market. Only market orders are supported
    as of now. More types of orders will be added.
    """

    client_order_id: str
    order_type: OrderType
    symbol: str
    price: Union[float, None]
    quantity: float
    side: MarketSide
    creation_time: datetime
