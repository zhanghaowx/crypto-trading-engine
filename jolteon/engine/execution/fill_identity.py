"""Stable internal identity for a venue execution."""

import json


def fill_identity(
    exchange: str, exchange_order_id: str, exchange_trade_id: str
) -> str:
    """Identify an execution independently of prices and process state."""
    if not all((exchange, exchange_order_id, exchange_trade_id)):
        raise ValueError(
            "Fill identity requires exchange, order, and trade IDs"
        )
    return json.dumps(
        [exchange, exchange_order_id, exchange_trade_id], separators=(",", ":")
    )
