import logging
import uuid
from collections import deque

from blinker import signal

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeater
from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.core.time.time_manager import time_manager
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit
from crypto_trading_engine.strategy.bull_flag.bull_flag_opportunity import (
    BullFlagOpportunity,
)
from crypto_trading_engine.strategy.bull_flag.candlestick_pattern import (
    CandlestickPattern,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.strategy.core.strategy_order import StrategyOrder
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


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
        self.opportunity_event = signal("opportunity")
        self.open_orders = dict[str, StrategyOrder]()

    def on_candlestick(self, _: str, candlestick: Candlestick):
        # It shall be either an update on last candlestick or a new
        # candlestick.

        # Merge candlesticks
        assert (
            len(self.history) == 0
            or self.history[-1].start_time <= candlestick.start_time
        ), (
            "Candlesticks shall be sent in time order! "
            f"Last candlestick in history: {self.history[-1].start_time}, "
            f"current candlestick: {candlestick.start_time}"
        )

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
        self.try_buy(self.generate_buy_opportunity())
        self.try_close_positions()

    def on_fill(self, _: str, trade: Trade):
        logging.info(f"Received {trade} for {self.symbol}")

    def generate_buy_opportunity(self):
        # Don't make decisions until watching the market for a while
        if len(self.history) < self.history.maxlen:
            return BullFlagOpportunity()

        # Try search back N candlesticks and see if a bull flag pattern could
        # be found.
        for i in range(0, len(self.history)):
            opportunity = self.pattern_recognizer.is_bull_flag(
                candlesticks=list(self.history)[i:]
            )
            if opportunity:
                self.opportunity_event.send(
                    self.opportunity_event, opportunity=opportunity
                )
            if opportunity and opportunity.good():
                return opportunity
            # Keep searching until a good opportunity is found or all
            # possibilities are exhausted.

        return BullFlagOpportunity()

    def try_buy(self, opportunity: TradeOpportunity) -> bool:
        if not opportunity or not opportunity.good():
            return False

        assert (
            opportunity.stop_loss_price > 0.0
        ), "Stop loss price must be positive!"

        for limit in self.risk_limits:
            if not limit.can_send():
                return False
        for limit in self.risk_limits:
            limit.do_send()

        client_order_id = str(uuid.uuid4())
        order = Order(
            client_order_id=client_order_id,
            order_type=OrderType.MARKET_ORDER,
            symbol=self.symbol,
            price=None,
            quantity=0.01,
            side=MarketSide.BUY,
            creation_time=time_manager().now(),
        )
        self.open_orders[client_order_id] = StrategyOrder(
            opportunity=opportunity,
            open_order=order,
        )

        logging.info(
            f"Placed {order} with candlesticks at " f"{time_manager().now()}."
        )
        self.order_event.send(self.order_event, order=order)

        return True

    def try_close_positions(self) -> None:
        if len(self.open_orders) == 0:
            return

        assert len(self.history) == self.history.maxlen

        orders_to_delete = []
        for open_order in self.open_orders.values():
            order = Order(
                client_order_id=open_order.open_order.client_order_id,
                order_type=OrderType.MARKET_ORDER,
                symbol=open_order.open_order.symbol,
                price=None,
                quantity=open_order.open_order.quantity,
                side=MarketSide.SELL,
                creation_time=time_manager().now(),
            )

            if open_order.should_close_for_loss(self.history[-1].close):
                # crossed stop loss line, we need sell for limiting losses
                logging.warning(f"Placed {order} due to crossing stop loss.")
                orders_to_delete.append(order.client_order_id)
                self.order_event.send(self.order_event, order=order)
            elif open_order.should_close_for_profit(self.history[-1].close):
                # crossed profit line, we need sell for profit
                logging.info(f"Placed {order} for profit.")
                orders_to_delete.append(order.client_order_id)
                self.order_event.send(self.order_event, order=order)
            else:
                return

        self.open_orders = {
            key: value
            for key, value in self.open_orders.items()
            if value.open_order.client_order_id not in orders_to_delete
        }
