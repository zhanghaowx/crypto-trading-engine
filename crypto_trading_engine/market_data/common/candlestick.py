from datetime import datetime, timedelta
from typing import Union

import pytz


class Candlestick:
    PRIMARY_KEY = "start_time"

    def __init__(self, start: datetime, duration_in_seconds: float):
        """
        Candlestick displays the high, low, open, and close price of a
        security/cryptocurrency for a specific period.

        Args:
            start: Start time that the candlestick represents
            duration_in_seconds: Duration of the time period that the
                                 candlestick represents
        """
        self.start_time: datetime = start
        self.end_time: datetime = start + timedelta(
            seconds=duration_in_seconds
        )
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = float("inf")
        self.close: float = 0.0
        self.volume: float = 0.0

    def __repr__(self):
        return (
            f"Candlestick("
            f"Open={self.open}, "
            f"High={self.high}, "
            f"Low={self.low}, "
            f"Close={self.close}, "
            f"Volume={self.volume}, "
            f"StartTime={self.start_time}, "
            f"EndTime={self.end_time}, "
            f"ReturnPct={self.return_percentage()}"
            f")"
        )

    def add_trade(
        self,
        trade_price: float,
        trade_quantity: float,
        transaction_time: datetime,
    ):
        """
        Adds a new trade which falls in the time range of the candlestick.

        Args:
            trade_price: Price of the trade
            trade_quantity: Quantity of the trade
            transaction_time: Time of the transaction. Use current time if no
                              transaction time provided

        Returns:
            True if trade is successfully added to the candlestick. Otherwise
            False
        """
        if (
            transaction_time < self.start_time
            or transaction_time > self.end_time
        ):
            return False

        if self.volume == 0.0:
            self.open = trade_price

        self.high = max(self.high, trade_price)
        self.low = min(self.low, trade_price)
        self.close = trade_price
        self.volume += trade_quantity
        return True

    def is_completed(self, now: Union[datetime, None] = None):
        """
        Returns:
            Whether the candlestick is completed or it is still being built
        """

        return (now if now else datetime.now(pytz.utc)) >= self.end_time

    def is_bullish(self):
        """
        Returns:
            Whether the candlestick represents a bullish market
        """
        return self.close > self.open

    def is_bearish(self):
        """
        Returns:
            Whether the candlestick represents a bearish market
        """
        return self.close < self.open

    def return_percentage(self):
        """
        Returns:
            Rate of return if buy one share at open and sell at close
        """
        if self.open == 0.0:
            return 0.0
        return (self.close - self.open) / self.open
