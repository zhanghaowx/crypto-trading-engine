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
from crypto_trading_engine.strategy.bull_flag.bull_flag_pattern import (
    BullFlagPattern,
)
from crypto_trading_engine.strategy.bull_flag.bull_flag_round_trip import (
    BullFlagRoundTrip,
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
        self._parameters = parameters
        self._risk_limits = risk_limits
        self._pattern_recognizer = BullFlagPattern(parameters)

        # Signals to send out
        self._order_event = signal("order")
        self._opportunity_event = signal("opportunity")
        self._trade_result_event = signal("trade_result")

        # Records of orders and market data
        self._round_trips = list[BullFlagRoundTrip]()
        self._market_history = deque[Candlestick](
            maxlen=parameters.max_number_of_recent_candlesticks
        )

    def on_candlestick(self, _: str, candlestick: Candlestick):
        # It shall be either an update on last candlestick or a new
        # candlestick.

        # Merge candlesticks
        assert (
            len(self._market_history) == 0
            or self._market_history[-1].start_time <= candlestick.start_time
        ), (
            "Candlesticks shall be sent in time order! "
            f"Last candlestick in history: "
            f"{self._market_history[-1].start_time}, "
            f"current candlestick: {candlestick.start_time}"
        )

        if (
            len(self._market_history) == 0
            or self._market_history[-1].start_time < candlestick.start_time
        ):
            self._market_history.append(candlestick)
        else:
            assert (
                self._market_history[-1].start_time == candlestick.start_time
            )
            self._market_history[-1] = candlestick

        # Run bull flag strategy to make a decision
        self._try_buy(self._generate_buy_opportunity())
        self._try_close_positions()

    def on_fill(self, _: str, trade: Trade):
        logging.info(f"Received {trade} for {self.symbol}")

        if trade.side == MarketSide.BUY:
            found_round_trip = next(
                (
                    trip
                    for trip in self._round_trips
                    if trip.buy_order
                    and trip.buy_order.client_order_id == trade.client_order_id
                ),
                None,
            )

            assert (
                found_round_trip is not None
            ), f"No buy order located for a buy trade: {trade}"

            found_round_trip.buy_trades.append(trade)
            if found_round_trip.completed():
                self._trade_result_event.send(
                    self._trade_result_event,
                    round_trip=found_round_trip,
                )

        elif trade.side == MarketSide.SELL:
            found_round_trip = next(
                (
                    trip
                    for trip in self._round_trips
                    if trip.sell_order
                    and trip.sell_order.client_order_id
                    == trade.client_order_id
                ),
                None,
            )

            assert (
                found_round_trip is not None
            ), f"No sell order located for a sell trade: {trade}"

            found_round_trip.sell_trades.append(trade)
            if found_round_trip.completed():
                self._trade_result_event.send(
                    self._trade_result_event,
                    round_trip=found_round_trip,
                )
        else:
            assert False, f"Unexpected trade: {trade}"

    def _generate_buy_opportunity(self):
        # Don't make decisions until watching the market for a while
        if len(self._market_history) < self._market_history.maxlen:
            return BullFlagOpportunity()

        # Try search back N candlesticks and see if a bull flag pattern could
        # be found.
        for i in range(0, len(self._market_history)):
            opportunity = self._pattern_recognizer.is_bull_flag(
                candlesticks=list(self._market_history)[i:]
            )
            if opportunity:
                self._opportunity_event.send(
                    self._opportunity_event, opportunity=opportunity
                )
            if opportunity and opportunity.good(
                self._parameters.opportunity_score_cutoff
            ):
                return opportunity
            # Keep searching until a good opportunity is found or all
            # possibilities are exhausted.

        return BullFlagOpportunity()

    def _try_buy(self, opportunity: BullFlagOpportunity) -> bool:
        # Don't buy if opportunity is not good enough
        if not opportunity or not opportunity.good(
            self._parameters.opportunity_score_cutoff
        ):
            return False

        # Don't buy if we've already placed an order for the same bull flag
        for bull_flag_trip in self._round_trips:
            if bull_flag_trip.opportunity.start == opportunity.start:
                return False

        assert (
            opportunity.stop_loss_price > 0.0
        ), "Stop loss price must be positive!"

        for limit in self._risk_limits:
            if not limit.can_send():
                return False
        for limit in self._risk_limits:
            limit.do_send()

        order = Order(
            client_order_id=str(uuid.uuid4()),
            order_type=OrderType.MARKET_ORDER,
            symbol=self.symbol,
            price=None,
            quantity=0.01,
            side=MarketSide.BUY,
            creation_time=time_manager().now(),
        )
        self._round_trips.append(
            BullFlagRoundTrip(
                opportunity=opportunity,
                buy_order=order,
            )
        )

        logging.info(
            f"Placed {order} with candlesticks at " f"{time_manager().now()}."
        )
        self._order_event.send(self._order_event, order=order)

        return True

    def _try_close_positions(self) -> None:
        if len(self._round_trips) == 0:
            return

        assert len(self._market_history) == self._market_history.maxlen

        for round_trip in self._round_trips:
            # Skip if sell order has been placed
            if round_trip.sell_order:
                continue

            assert (
                round_trip.buy_order
            ), "Buy order has to be placed before sending a sell order!"

            sell_order = Order(
                client_order_id=str(uuid.uuid4()),
                order_type=OrderType.MARKET_ORDER,
                symbol=round_trip.buy_order.symbol,
                price=None,
                quantity=round_trip.buy_order.quantity,
                side=MarketSide.SELL,
                creation_time=time_manager().now(),
            )

            if round_trip.should_sell_for_loss(self._market_history[-1].close):
                # crossed stop loss line, we need sell for limiting losses
                logging.warning(f"Placed {sell_order} for limiting loss.")

                round_trip.sell_order = sell_order
                self._order_event.send(self._order_event, order=sell_order)
            elif round_trip.should_sell_for_profit(
                self._market_history[-1].close
            ):
                # crossed profit line, we need sell for profit
                logging.info(f"Placed {sell_order} for profit.")

                round_trip.sell_order = sell_order
                self._order_event.send(self._order_event, order=sell_order)
            else:
                return
