import logging
import uuid
from collections import deque
from datetime import datetime
from itertools import islice

import pytz
from blinker import signal

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit
from crypto_trading_engine.strategy.bull_flag.candlestick_pattern import (
    CandlestickPattern,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters


class BullFlagStrategy(Heartbeater):
    def __init__(
        self,
        symbol: str,
        risk_limits: list[IRiskLimit],
        parameters: Parameters,
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
        self.symbol = symbol
        self.risk_limits = risk_limits
        self.params = parameters
        self.history = deque[Candlestick](
            maxlen=parameters.max_number_of_recent_candlesticks
        )
        self.pattern_recognizer = CandlestickPattern(parameters)
        self.order_event = signal("order")

    def on_candlestick(self, _: str, candlestick: Candlestick):
        # It shall be either an update on last candlestick or a new
        # candlestick.

        # Merge candlesticks
        assert (
            len(self.history) == 0
            or self.history[-1].start_time <= candlestick.start_time
        ), "Candlesticks shall be sent in time order!"

        if (
            len(self.history) == 0
            or self.history[-1].start_time < candlestick.start_time
        ):
            self.history.append(candlestick)
        elif self.history[-1].start_time == candlestick.start_time:
            self.history[-1] = candlestick
        else:
            raise Exception("Candlesticks shall be sent in time order!")

        # Run bull flag strategy to make a decision
        if self.should_buy():
            self.try_buy()

    def on_fill(self, _: str, trade: Trade):
        logging.info(f"Received {trade} for {self.symbol}")

    def should_buy(self):
        # Don't make decisions until watching the market for a while
        if len(self.history) < self.history.maxlen:
            return False

        for i in range(0, len(self.history)):
            opportunity = self.pattern_recognizer.is_bull_flag(
                candlesticks=list(islice(self.history, i, None))
            )
            if opportunity.score > 0:
                return True

        return False

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
            creation_time=datetime.now(pytz.utc),
        )
        logging.info(f"Placed {order} with candlesticks {self.history}.")
        self.order_event.send(self.order_event, order=order)
        return True
