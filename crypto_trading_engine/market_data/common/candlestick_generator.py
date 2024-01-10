import logging

from crypto_trading_engine.market_data.common.candlestick import Candlestick
from crypto_trading_engine.market_data.core.trade import Trade


class CandlestickGenerator:
    def __init__(self, interval_in_seconds=60):
        self.current_candlestick = None
        self.interval_in_seconds = interval_in_seconds

        assert (
            self.interval_in_seconds <= 60
            or self.interval_in_seconds % 60 == 0
        ), f"Unsupported Candlestick Duration {self.interval_in_seconds}!"

    def on_trade(self, trade: Trade) -> list[Candlestick]:
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
