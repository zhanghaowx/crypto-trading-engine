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

        if not self.current_candlestick:
            self._set_current_candlestick(trade)
        else:
            while not self.current_candlestick.add_trade(
                trade.price, trade.quantity, trade.transaction_time
            ):
                assert self.current_candlestick.is_completed(), (
                    f"{self.current_candlestick} is expected to be completed "
                    f"at {time_manager().now()} after seeing {trade}"
                )
                self._complete_candlestick(candlesticks)
                self._move_to_next_candlestick()

        # Finally, the current candlestick will include trade and we should
        # report it as well.
        candlesticks.append(self.current_candlestick)
        return candlesticks

    def _set_current_candlestick(self, trade):
        """
        Sets the current candlestick time range based on the 1st seen trade.
        This is the starting of our candlestick history.
        """

        assert self.current_candlestick is None

        # Calculate the start time of the new candlestick
        start_time = trade.transaction_time.replace(
            second=trade.transaction_time.second
            // self.interval_in_seconds
            * self.interval_in_seconds,
            microsecond=0,
        )

        # Create new candlestick for the trade
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
        assert (
            trade_added
        ), "Trade should be added to a newly created candlestick successfully"

    def _complete_candlestick(self, candlesticks: list[Candlestick]) -> None:
        """
        Mark the current candlestick as completed

        Returns:
            None
        """
        logging.debug(
            f"Generated Completed Candlestick: " f"{self.current_candlestick}"
        )
        # In some case, we may get trades far away from each other. And there
        # will be multiple empty candlesticks between them. For those
        # special candlesticks we still want to report them and maintain a
        # continuous time series.
        if self.current_candlestick.volume == 0:
            candlesticks.append(self.current_candlestick)

    def _move_to_next_candlestick(self):
        """
        Set the current candlestick to be the next expected candlestick after
        it.

        Returns:
            None
        """
        assert self.current_candlestick is not None
        self.current_candlestick = Candlestick(
            start=self.current_candlestick.end_time,
            duration_in_seconds=self.interval_in_seconds,
            open=self.current_candlestick.close,
            high=self.current_candlestick.close,
            close=self.current_candlestick.close,
            low=self.current_candlestick.close,
            volume=0,
        )
