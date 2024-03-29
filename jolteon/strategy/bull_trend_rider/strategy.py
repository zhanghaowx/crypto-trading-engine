import logging

from jolteon.core.event.signal import signal, subscribe
from jolteon.core.event.signal_subscriber import SignalSubscriber
from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.candlestick_list import CandlestickList
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.risk_limit.risk_limit import IRiskLimit
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
from jolteon.strategy.bull_trend_rider.trade_opportunity import (
    TradeOpportunity,
)
from jolteon.strategy.bull_trend_rider.trade_record import TradeRecord
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)
from jolteon.strategy.core.patterns.shooting_star.pattern import (
    ShootingStarPattern,
)


class BullTrendRiderStrategy(Heartbeater, SignalSubscriber):
    def __init__(
        self,
        symbol: str,
        risk_limits: list[IRiskLimit],
        parameters: StrategyParameters,
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
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.symbol = symbol
        self._parameters = parameters
        self._risk_limits = risk_limits

        # Signals to send out
        self.order_event = signal("order")
        self.opportunity_event = signal("bull_trend_rider_opportunity")
        self.trade_result_event = signal("bull_trend_rider_trade_result")

        # Records of orders and market data
        self._round_trips = list[TradeRecord]()
        self._market_history = CandlestickList(
            max_length=parameters.max_number_of_recent_candlesticks
        )

    @subscribe("calculated_candlestick_feed")
    def on_candlestick(self, _: str, candlestick: Candlestick):
        self._market_history.add_candlestick(candlestick)

        # Run bull flag strategy to make a decision
        self._try_close_positions()

    @subscribe("bull_flag")
    def on_bull_flag_pattern(self, _: str, pattern: BullFlagPattern):
        if pattern.result != RecognitionResult.BULL_FLAG:
            return

        opportunity = TradeOpportunity(
            pattern=pattern,
            history=self._market_history,
            params=self._parameters,
        )

        self.opportunity_event.send(
            self.opportunity_event, opportunity=opportunity
        )

        self._try_buy(opportunity)

    @subscribe("shooting_star")
    def on_shooting_star_pattern(self, _: str, pattern: ShootingStarPattern):
        """
        A shooting pattern appears after a bull flag pattern might indicate the
        end of the bullish trend. Sell unclosed positions as soon as possible.

        Args:
            _: Unique identifier of the sender
            pattern: Details about the shooting star pattern

        Returns:
            None

        """
        self._try_close_positions(force=True)

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        def _matching_trip_in(order_field: str) -> TradeRecord | None:
            return next(
                (
                    trip
                    for trip in self._round_trips
                    if getattr(trip, order_field)
                    and getattr(trip, order_field).client_order_id
                    == trade.client_order_id
                ),
                None,
            )

        if trade.side == MarketSide.BUY:
            found_round_trip = _matching_trip_in("buy_order")
            logging.info(f"Received {trade} for {vars(found_round_trip)}")
            assert (
                found_round_trip is not None
            ), f"No buy order located for a buy trade: {trade}"

            found_round_trip.buy_trades.append(trade)
            if found_round_trip.completed():
                self.trade_result_event.send(
                    self.trade_result_event,
                    round_trip=found_round_trip,
                )

        elif trade.side == MarketSide.SELL:
            found_round_trip = _matching_trip_in("sell_order")
            logging.info(f"Received {trade} for {vars(found_round_trip)}")

            assert (
                found_round_trip is not None
            ), f"No sell order located for a sell trade: {trade}"

            found_round_trip.sell_trades.append(trade)
            if found_round_trip.completed():
                self.trade_result_event.send(
                    self.trade_result_event,
                    round_trip=found_round_trip,
                )
        else:
            assert False, f"Unexpected trade: {trade}"

    def _try_buy(self, opportunity: TradeOpportunity) -> bool:
        # Don't buy if opportunity is not good enough
        if not opportunity or not opportunity.good(
            self._parameters.opportunity_score_cutoff
        ):
            return False

        # Don't buy if we've already placed an order for the same bull flag
        for bull_flag_trip in self._round_trips:
            if (
                bull_flag_trip.opportunity.bull_flag_pattern.start
                == opportunity.bull_flag_pattern.start
            ):
                return False

        assert (
            opportunity.stop_loss_price > 0.0
        ), "Stop loss price must be positive!"

        for limit in self._risk_limits:
            if not limit.can_send():
                return False

        buy_order = Order(
            client_order_id=str(id_generator().next()),
            order_type=OrderType.MARKET_ORDER,
            symbol=self.symbol,
            price=None,
            quantity=self._parameters.min_quantity,
            side=MarketSide.BUY,
            creation_time=time_manager().now(),
        )
        self._round_trips.append(
            TradeRecord(
                opportunity=opportunity,
                buy_order=buy_order,
            )
        )

        logging.info(
            f"Placed {buy_order} with candlesticks at "
            f"{time_manager().now()}."
        )
        self._send_order(buy_order)

        return True

    def _try_close_positions(self, force: bool = False) -> None:
        if len(self._round_trips) == 0:
            return

        for round_trip in self._round_trips:
            # Skip if sell order has been placed
            if round_trip.sell_order:
                continue

            # Skip if buy orders has not been confirmed yet
            if not round_trip.buy_trades:
                continue

            assert (
                round_trip.buy_order
            ), "Buy order has to be placed before sending a sell order!"

            sell_order = Order(
                client_order_id=str(id_generator().next()),
                order_type=OrderType.MARKET_ORDER,
                symbol=round_trip.buy_order.symbol,
                price=None,
                quantity=round_trip.buy_order.quantity,
                side=MarketSide.SELL,
                creation_time=time_manager().now(),
            )

            latest_market_price = self._market_history[-1].close
            if round_trip.should_sell_for_loss(latest_market_price):
                # crossed stop loss line, we need sell for limiting losses
                logging.warning(
                    f"Placed {sell_order} for limiting loss "
                    f"when last market trade is at "
                    f"{latest_market_price} "
                    f"and our trade record is "
                    f"{vars(round_trip)}."
                )

                round_trip.sell_order = sell_order
                self._send_order(sell_order)
            elif round_trip.should_sell_for_profit(latest_market_price):
                # crossed profit line, we need sell for profit
                logging.info(
                    f"Placed {sell_order} for profit "
                    f"with expectations to be traded near "
                    f"{latest_market_price}."
                )

                round_trip.sell_order = sell_order
                self._send_order(sell_order)
            elif force:
                logging.info(f"Placed {sell_order} for other reasons.")

                round_trip.sell_order = sell_order
                self._send_order(sell_order)
            else:
                continue

    def _send_order(self, order):
        for limit in self._risk_limits:
            limit.do_send()
        self.order_event.send(self.order_event, order=order)
