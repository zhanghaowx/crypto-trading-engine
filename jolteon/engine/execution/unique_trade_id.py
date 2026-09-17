"""Globally unique identity for a trade or fill."""

import json


def unique_trade_id(
    exchange: str, exchange_order_id: str, exchange_execution_id: str
) -> str:
    """Identify a trade independently of its price and process state."""
    if not all((exchange, exchange_order_id, exchange_execution_id)):
        raise ValueError(
            "Unique trade ID requires exchange, order, and trade IDs"
        )
    return json.dumps(
        [exchange, exchange_order_id, exchange_execution_id],
        separators=(",", ":"),
    )
