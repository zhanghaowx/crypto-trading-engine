from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater


class ExitStrategy(Heartbeater):
    """
    ExitStrategy is a type of strategy to help close open positions. It could
    close a position for profit or loss:
        - Profit: When price starts moving in a direction against us
        - Loss: Either the entire account stop loss condition is met,
                or the price is worse than the last support/resist price
    """

    pass
