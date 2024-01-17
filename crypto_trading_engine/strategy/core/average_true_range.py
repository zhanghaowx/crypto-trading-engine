from crypto_trading_engine.market_data.core.candlestick import Candlestick


def calculate_atr(candlesticks: list[Candlestick], period):
    assert len(candlesticks) <= period, (
        f"Insufficient data to calculate ATR: "
        f"trying to calculate ATR for {len(candlesticks)} candlesticks "
        f"with a period {period}"
    )

    true_ranges = []

    for i in range(len(candlesticks) - period + 1, len(candlesticks)):
        high_low = candlesticks[i].high - candlesticks[i].low
        high_close_prev = abs(candlesticks[i].high - candlesticks[i - 1].close)
        low_close_prev = abs(candlesticks[i].low - candlesticks[i - 1].close)
        true_range = max(high_low, high_close_prev, low_close_prev)
        true_ranges.append(true_range)

    atr = sum(true_ranges) / period

    return atr
