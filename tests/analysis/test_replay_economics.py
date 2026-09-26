import pandas as pd

from jolteon.analysis.replay_economics import replay_economics


def test_covered_and_missing_markouts():
    events = pd.DataFrame(
        [
            {
                "channel": "order_fill",
                "timestamp": 0.0,
                "payload": {
                    "symbol": "BTC/USD",
                    "side": "BUY",
                    "price": 10.0,
                    "quantity": 2.0,
                    "fee": 1.0,
                },
            },
            {
                "channel": "fair_price",
                "timestamp": 0.1,
                "payload": {
                    "symbol": "BTC/USD",
                    "model": "AdjustedFairPriceModel",
                    "bid_fair_price": 11.0,
                    "ask_fair_price": 13.0,
                },
            },
        ]
    )
    result = replay_economics(events)
    assert result["notional"] == 20
    assert result["fees"] == 1
    assert result["realized_pnl"] == -1
    assert result["markouts"]["100ms"] == {
        "covered_fills": 1,
        "gross_usd": 4.0,
        "net_usd": 3.0,
    }
    assert result["markouts"]["1s"]["net_usd"] is None
    assert replay_economics(pd.DataFrame())["fill_count"] == 0
