from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import ClassVar, Union

from jolteon.core.side import MarketSide


class OrderType(Enum):
    MARKET_ORDER = 1


@dataclass
class Order:
    """
    Represents an order placed in the market. Only market orders are supported
    as of now. More types of orders will be added.
    """

    PRIMARY_KEY: ClassVar[str] = "client_order_id"
    client_order_id: str
    order_type: OrderType
    symbol: str
    price: Union[float, None]
    quantity: float
    side: MarketSide
    creation_time: datetime
