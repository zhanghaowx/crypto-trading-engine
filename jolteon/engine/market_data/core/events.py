from jolteon.engine.core.event.signal import signal


class Events:
    """
    A list of common events provided by most exchanges' in their
    market data feeds.
    """

    channel_heartbeat = signal("channel_heartbeat_feed")
    bbo = signal("bbo_feed")
    market_trade = signal("market_trade_feed")
    order_book = signal("order_book_feed")
    order_book_update = signal("order_book_update_feed")
    instrument = signal("instrument_feed")
