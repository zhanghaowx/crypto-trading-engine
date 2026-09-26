"""Existing fill economics derived from replay comparison events."""

import pandas as pd

from jolteon.analysis.markouts import (
    HORIZONS,
    compute_markout,
    derive_fill_markouts,
)
from jolteon.analysis.pnl import realized_pnl


def replay_economics(events: pd.DataFrame) -> dict:
    fills = []
    prices = []
    for event in events.itertuples(index=False):
        payload = dict(event.payload)
        payload["timestamp"] = event.timestamp
        if event.channel == "order_fill":
            payload["fill_price"] = payload.pop("price")
            payload["fill_qty"] = payload.pop("quantity")
            payload["fair_price_model"] = "AdjustedFairPriceModel"
            fills.append(payload)
        elif event.channel == "fair_price":
            prices.append(payload)
    if not fills:
        return {
            "fill_count": 0,
            "notional": 0.0,
            "fees": 0.0,
            "realized_pnl": 0.0,
            "markouts": {},
        }
    frame = pd.DataFrame(fills)
    enriched = derive_fill_markouts(frame, pd.DataFrame(prices))
    markouts = {}
    for horizon in HORIZONS:
        gross = compute_markout(enriched, horizon) * enriched["fill_qty"]
        covered = gross.notna()
        markouts[horizon] = {
            "covered_fills": int(covered.sum()),
            "gross_usd": float(gross[covered].sum())
            if covered.any()
            else None,
            "net_usd": float(
                (gross[covered] - enriched.loc[covered, "fee"]).sum()
            )
            if covered.any()
            else None,
        }
    return {
        "fill_count": len(frame),
        "notional": float((frame["fill_price"] * frame["fill_qty"]).sum()),
        "fees": float(frame["fee"].sum()),
        "realized_pnl": realized_pnl(frame),
        "markouts": markouts,
    }
