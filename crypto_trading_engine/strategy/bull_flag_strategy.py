import logging
import uuid
from collections import deque
from typing import Union

import pandas as pd
from blinker import signal

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.common.candlestick import Candlestick
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit


class BullFlagStrategy(Heartbeater):
    def __init__(
        self,
        symbol: str,
        risk_limits: list[IRiskLimit],
        max_number_of_recent_candlesticks: int = 2,
        min_return_of_extreme_bullish_candlesticks: float = 0.1,
        min_return_of_active_candlesticks: float = 0.05,
    ):
        """
        Idea take from the book "How to day-trade for a living",
        chapter 7: important day trading strategies.

        This strategy requires a fast execution platform and usually works
        effectively on low float stocks under $10. Its performance in
        cryptocurrency markets is under evaluation.

        In summary:
            1. Find a time when the price is surging up.
            2. Wait during the consolidation period.
            3. As soon as prices are moving over the high of the consolidation
               candlesticks, buy.
            4. Sell half of the position and take a profit on the way up.
            5. Sell remaining positions when sellers is about to gain control.

        Restrictions:
            1. This strategy only trades one instrument
        """
        super().__init__(type(self).__name__, interval_in_seconds=5)
        self.max_number_of_past_candlesticks = (
            max_number_of_recent_candlesticks
        )
        self.min_return_of_active_candlesticks = (
            min_return_of_active_candlesticks
        )
        self.min_return_of_extreme_bullish_candlesticks = (
            min_return_of_extreme_bullish_candlesticks
        )
        self.history = deque[Candlestick](
            maxlen=max_number_of_recent_candlesticks
        )
        self.symbol = symbol
        self.risk_limits = risk_limits
        self.active_candlestick: Union[None, Candlestick] = None
        self.order_event = signal("order")

    def on_candlestick(self, _: str, candlestick: Candlestick):
        if candlestick.is_completed():
            self.history.append(candlestick)
        else:
            self.active_candlestick = candlestick

        if self.should_buy():
            self.try_buy()

    def on_fill(self, _: str, trade: Trade):
        logging.info(f"Received {trade} for {self.symbol}")

    def gather_features(self):
        """
        Base on history candlestick and the most recent active candlestick,
        create a list of features

        Returns:
            A list of features to send to strategy model
        """
        all_candlesticks = [x.__dict__ for x in self.history]
        all_candlesticks.append(self.active_candlestick.__dict__)
        return pd.DataFrame(all_candlesticks)

    def should_buy(self):
        # Don't make decisions until watching the market for a while
        if len(self.history) < self.history.maxlen:
            return False

        # Don't consider it as an opportunity for bull flag strategy
        # if the last candlestick is not extremely bullish
        if (
            self.history[-1].return_percentage()
            < self.min_return_of_extreme_bullish_candlesticks
        ):
            return False

        # Don't consider it as an opportunity for bull flag strategy
        # if the current candlestick is not trending bullish
        if (
            self.active_candlestick.return_percentage()
            < self.min_return_of_active_candlesticks
        ):
            return False

        return True

    def try_buy(self):
        for limit in self.risk_limits:
            if not limit.can_send():
                return False
        for limit in self.risk_limits:
            limit.do_send()

        order = Order(
            client_order_id=str(uuid.uuid4()),
            order_type=OrderType.MARKET_ORDER,
            symbol=self.symbol,
            price=None,
            quantity=0.01,
            side=MarketSide.BUY,
        )
        logging.info(
            f"Placed {order} with history {self.history} and "
            f"current active/incomplete candlestick "
            f"{self.active_candlestick}"
        )
        self.order_event.send(self.order_event, order=order)
        return True
