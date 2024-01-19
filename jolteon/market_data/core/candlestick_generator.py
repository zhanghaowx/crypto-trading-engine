import logging

from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.trade import Trade


class CandlestickGenerator:
    def __init__(self, interval_in_seconds=60):
        self.current_candlestick = None
        self.interval_in_seconds = interval_in_seconds

        assert (
            self.interval_in_seconds <= 60
            or self.interval_in_seconds % 60 == 0
        ), f"Unsupported Candlestick Duration {self.interval_in_seconds}!"

    def on_market_trade(self, trade: Trade) -> list[Candlestick]:
        """
        Generates candlestick(s) for a given market trade. Returns 1
        candlestick if the market trade happens within the time frame of the
        current candlestick. Otherwise, returns 2 candlesticks, one for
        previous time frame and one (incomplete) for the current time frame.

        Args:
            trade: Market trade to generate candlesticks for.
        Returns:
            1 ~ 2 candlesticks.
        """
        candlesticks: list[Candlestick] = []

        if self.current_candlestick and self.current_candlestick.add_trade(
            trade.price, trade.quantity, trade.transaction_time
        ):
            candlesticks.append(self.current_candlestick)
        else:
            # Deliver previous candlestick before starting a new one
            if self.current_candlestick:
                assert not self.current_candlestick.add_trade(
                    trade.price, trade.quantity, trade.transaction_time
                )
                logging.info(
                    f"Generated Completed Candlestick: "
                    f"{self.current_candlestick}"
                )
                assert self.current_candlestick.is_completed(), (
                    f"{self.current_candlestick} is expected to be completed "
                    f"at {time_manager().now()} after seeing {trade}"
                )
                candlesticks.append(self.current_candlestick)

            # Calculate the start time of the new candlestick
            start_time = trade.transaction_time.replace(
                second=trade.transaction_time.second
                // self.interval_in_seconds
                * self.interval_in_seconds,
                microsecond=0,
            )

            # Create new candlestick
            self.current_candlestick = Candlestick(
                start_time, self.interval_in_seconds
            )
            assert (
                self.current_candlestick.start_time
                <= trade.transaction_time
                <= self.current_candlestick.end_time
            )

            trade_added = self.current_candlestick.add_trade(
                trade.price, trade.quantity, trade.transaction_time
            )
            assert trade_added, (
                "Trade should be added to a newly created "
                "candlestick successfully"
            )
            candlesticks.append(self.current_candlestick)

        return candlesticks
