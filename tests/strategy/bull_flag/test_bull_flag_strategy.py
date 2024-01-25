import unittest
from copy import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytz
from blinker import ANY

from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.risk_limit.risk_limit import IRiskLimit
from jolteon.strategy.bull_trend_rider.strategy import (
    BullFlagStrategy,
)
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)
from jolteon.strategy.bull_trend_rider.trade_opportunity import (
    TradeOpportunity,
)
from jolteon.strategy.bull_trend_rider.trade_record import (
    TradeRecord,
)
from jolteon.strategy.core.patterns.bull_flag.pattern import (
    BullFlagPattern,
    RecognitionResult,
)
from jolteon.strategy.core.patterns.shooting_star.pattern import (
    ShootingStarPattern,
)
from jolteon.strategy.core.trade_opportunity import TradeOpportunityCore


class MockRiskLimits(IRiskLimit):
    def __init__(self, always_allow: bool = False):
        self.always_allow = always_allow

    def can_send(self):
        return self.always_allow

    def do_send(self):
        pass


class BullFlagStrategyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.candlesticks = [
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=0),
                duration_in_seconds=60,
                open=1,
                low=1,
                close=10,
                high=10,
                volume=100,
            ),
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=1),
                duration_in_seconds=60,
                open=10,
                low=1,
                close=11,
                high=12,
                volume=100,
            ),
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=2),
                duration_in_seconds=60,
                open=11,
                low=1,
                close=12,
                high=13,
                volume=100,
            ),
        ]
        self.bull_flag_pattern = BullFlagPattern(
            bull_flag_candlestick=self.candlesticks[0],
            consolidation_period_candlesticks=self.candlesticks[1:],
        )
        self.bull_flag_pattern.result = RecognitionResult.BULL_FLAG

        self.orders = list[Order]()
        self.opportunities = list[TradeOpportunity]()

        self.bull_flag_strategy = BullFlagStrategy(
            "ETH-USD",
            risk_limits=[MockRiskLimits(True)],
            parameters=StrategyParameters(
                max_number_of_recent_candlesticks=4,
                opportunity_score_cutoff=0.0,
            ),
        )
        self.round_trip = TradeRecord(
            opportunity=TradeOpportunity(
                pattern=self.bull_flag_pattern,
                target_reward_risk_ratio=2,
                adjusted_atr=1,
            ),
            buy_order=self.create_mock_order(MarketSide.BUY),
        )
        self.round_trip.buy_trades.append(
            self.create_mock_trade(1.0, MarketSide.BUY)
        )

        self.bull_flag_strategy.order_event.connect(self.on_order)
        self.bull_flag_strategy.opportunity_event.connect(self.on_opportunity)

    def on_order(self, sender: str, order: Order):
        self.orders.append(order)

    def on_opportunity(self, sender: str, opportunity: TradeOpportunity):
        self.opportunities.append(opportunity)

    @staticmethod
    def create_mock_timestamp():
        return datetime(
            year=2024,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=pytz.utc,
        )

    @staticmethod
    def create_mock_order(market_side: MarketSide):
        return Order(
            client_order_id="mock_id",
            symbol="BTC-USD",
            order_type=OrderType.MARKET_ORDER,
            side=market_side,
            price=1.0,
            quantity=1.0,
            creation_time=BullFlagStrategyTest.create_mock_timestamp(),
        )

    @staticmethod
    def create_mock_trade(
        price: float = 1.0, market_side: MarketSide = MarketSide.BUY
    ):
        return Trade(
            trade_id=0,
            client_order_id="mock_id",
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=market_side,
            price=price,
            quantity=1.0,
            transaction_time=BullFlagStrategyTest.create_mock_timestamp(),
        )

    async def test_buy_on_candlestick(self):
        # Arrange

        # Act
        for i in range(5, 0, -1):
            candlestick = Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                - timedelta(minutes=i),
                duration_in_seconds=60,
                open=10,
                low=1,
                close=11,
                high=12,
                volume=100,
            )
            self.bull_flag_strategy.on_candlestick("mock_sender", candlestick)

        self.bull_flag_strategy.on_bull_flag_pattern(
            "mock_sender", self.bull_flag_pattern
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy.order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.orders))
        self.assertEqual(MarketSide.BUY, self.orders[0].side)
        self.assertEqual(OrderType.MARKET_ORDER, self.orders[0].order_type)
        self.assertEqual(1, len(self.opportunities))

        # Resend the same candlesticks again should not trigger a new order
        self.bull_flag_strategy.on_bull_flag_pattern(
            "mock_sender", self.bull_flag_pattern
        )

        # Assert
        self.assertEqual(1, len(self.orders))
        self.assertEqual(2, len(self.opportunities))

    async def test_sell_for_limit_loss_on_candlestick(self):
        # Arrange
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[0]
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[1]
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )
        self.assertEqual(0, len(self.orders))

        self.round_trip.opportunity.stop_loss_price = (
            self.candlesticks[2].close + 0.01
        )
        self.round_trip.opportunity.profit_price = 1.0
        self.bull_flag_strategy._round_trips.append(self.round_trip)

        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))
        self.assertFalse(self.bull_flag_strategy._round_trips[0].completed())

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy.order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))

        sell_order = self.orders[-1]
        self.assertEqual(1, len(self.orders))
        self.assertNotEqual("mock_id", sell_order.client_order_id)
        self.assertEqual(OrderType.MARKET_ORDER, sell_order.order_type)
        self.assertEqual("BTC-USD", sell_order.symbol)
        self.assertEqual(None, sell_order.price)
        self.assertEqual(1, sell_order.quantity)
        self.assertEqual(MarketSide.SELL, sell_order.side)
        self.assertLess(
            datetime(2024, 1, 1, tzinfo=pytz.utc), sell_order.creation_time
        )

    async def test_sell_for_profit_on_candlestick(self):
        # Arrange
        for i in range(0, 3):
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[i]
            )
        self.assertEqual(0, len(self.orders))

        self.round_trip.opportunity.stop_loss_price = 1.0
        self.round_trip.opportunity.profit_price = (
            self.candlesticks[2].close - 0.01
        )
        self.bull_flag_strategy._round_trips.append(self.round_trip)
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))
        self.assertFalse(self.bull_flag_strategy._round_trips[0].completed())

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy.order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))

        sell_order = self.orders[-1]
        self.assertEqual(1, len(self.orders))
        self.assertNotEqual("mock_id", sell_order.client_order_id)
        self.assertEqual(OrderType.MARKET_ORDER, sell_order.order_type)
        self.assertEqual("BTC-USD", sell_order.symbol)
        self.assertEqual(None, sell_order.price)
        self.assertEqual(1, sell_order.quantity)
        self.assertEqual(MarketSide.SELL, sell_order.side)
        self.assertLess(
            datetime(2024, 1, 1, tzinfo=pytz.utc), sell_order.creation_time
        )

    async def test_sell_for_shooting_star(self):
        # Arrange
        for i in range(0, 3):
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[i]
            )
        self.assertEqual(0, len(self.orders))

        self.round_trip.opportunity.stop_loss_price = 10000
        self.round_trip.opportunity.profit_price = 10000
        self.bull_flag_strategy._round_trips.append(self.round_trip)
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))
        self.assertFalse(self.bull_flag_strategy._round_trips[0].completed())

        # Act
        self.bull_flag_strategy.on_shooting_star_pattern(
            "mock_sender",
            ShootingStarPattern(
                shooting_star=self.candlesticks[2],
                body_ratio=0.01,
                upper_shadow_ratio=10.0,
                lower_shadow_ratio=0.01,
            ),
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy.order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))

        sell_order = self.orders[-1]
        self.assertEqual(1, len(self.orders))
        self.assertNotEqual("mock_id", sell_order.client_order_id)
        self.assertEqual(OrderType.MARKET_ORDER, sell_order.order_type)
        self.assertEqual("BTC-USD", sell_order.symbol)
        self.assertEqual(None, sell_order.price)
        self.assertEqual(1, sell_order.quantity)
        self.assertEqual(MarketSide.SELL, sell_order.side)
        self.assertLess(
            datetime(2024, 1, 1, tzinfo=pytz.utc), sell_order.creation_time
        )

    async def test_on_fill(self):
        # Act
        self.bull_flag_strategy = BullFlagStrategy(
            "ETH-USD",
            risk_limits=[MockRiskLimits()],
            parameters=StrategyParameters(),
        )
        self.round_trip.buy_trades.clear()
        self.round_trip.sell_trades.clear()
        self.bull_flag_strategy._round_trips.append(self.round_trip)

        # Buys
        self.bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.0)
        )
        self.bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.1)
        )
        self.bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.2)
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy.order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.bull_flag_strategy._round_trips))
        self.assertEqual(
            3, len(self.bull_flag_strategy._round_trips[0].buy_trades)
        )

        # Sells
        self.bull_flag_strategy._round_trips[
            0
        ].sell_order = self.create_mock_order(MarketSide.SELL)
        self.bull_flag_strategy.on_fill(
            "mock_sender",
            BullFlagStrategyTest.create_mock_trade(1.0, MarketSide.SELL),
        )
        self.bull_flag_strategy.on_fill(
            "mock_sender",
            BullFlagStrategyTest.create_mock_trade(1.1, MarketSide.SELL),
        )
        self.bull_flag_strategy.on_fill(
            "mock_sender",
            BullFlagStrategyTest.create_mock_trade(1.2, MarketSide.SELL),
        )

    async def test_buy_order_blocked_by_risk_limits(self):
        # Risk Limit allows all

        mock_limit = MagicMock()
        mock_limit.can_send.return_value = False
        self.bull_flag_strategy._risk_limits = [mock_limit]
        # noinspection PyTypeChecker
        self.bull_flag_strategy._try_buy(
            opportunity=TradeOpportunityCore(
                score=1.0,
                stop_loss_price=0.1,
                profit_price=10,
            ),
        )
        self.assertEqual(0, len(self.orders))
        mock_limit.do_send.assert_not_called()

        # Risk Limit blocks all

        mock_limit = MagicMock()
        mock_limit.can_send.return_value = True
        self.bull_flag_strategy._risk_limits = [mock_limit]
        # noinspection PyTypeChecker
        self.bull_flag_strategy._try_buy(
            opportunity=TradeOpportunityCore(
                score=1.0,
                stop_loss_price=0.1,
                profit_price=10,
            ),
        )
        self.assertEqual(1, len(self.orders))
        mock_limit.do_send.assert_called_once()

    async def test_sell_order_not_blocked_by_risk_limits(self):
        mock_limit = MagicMock()
        mock_limit.can_send.return_value = False
        self.bull_flag_strategy._risk_limits = [mock_limit]

        for i in range(0, 3):
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[i]
            )

        self.round_trip.opportunity.stop_loss_price = 100
        self.bull_flag_strategy._round_trips.append(self.round_trip)
        self.bull_flag_strategy._round_trips.append(copy(self.round_trip))
        self.bull_flag_strategy._round_trips.append(copy(self.round_trip))

        self.bull_flag_strategy._try_close_positions()
        self.assertEqual(3, len(self.orders))
        mock_limit.do_send.assert_has_calls([call(), call(), call()])

        # Invoke the function again won't create more orders
        self.bull_flag_strategy._try_close_positions()
        self.assertEqual(3, len(self.orders))
        mock_limit.do_send.assert_has_calls([call(), call(), call()])
