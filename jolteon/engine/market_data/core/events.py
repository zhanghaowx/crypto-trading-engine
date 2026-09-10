from jolteon.engine.core.event.signal import signal


class Events:
    """
    A list of common events provided by most exchanges' in their
    market data feeds.
    """

    channel_heartbeat = signal("channel_heartbeat_feed")
    ticker = signal("ticker_feed")
    market_trade = signal("market_trade_feed")
