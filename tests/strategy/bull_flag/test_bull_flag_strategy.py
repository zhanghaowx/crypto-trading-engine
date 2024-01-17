import unittest
from datetime import datetime, timedelta

import pytz
from blinker import ANY

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit
from crypto_trading_engine.strategy.bull_flag.bull_flag_opportunity import (
    BullFlagOpportunity,
)
from crypto_trading_engine.strategy.bull_flag.bull_flag_strategy import (
    BullFlagStrategy,
)
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.strategy.bull_flag.open_position import OpenPosition


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
                high=10,
                low=1,
                open=1,
                close=10,
                volume=100,
            ),
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=1),
                duration_in_seconds=60,
                high=10,
                low=1,
                open=10,
                close=11,
                volume=100,
            ),
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=2),
                duration_in_seconds=60,
                high=10,
                low=1,
                open=11,
                close=12,
                volume=100,
            ),
        ]
        self.orders = list[Order]()
        self.opportunities = list[BullFlagOpportunity]()
        self.bull_flag_strategy = BullFlagStrategy(
            "ETH-USD",
            risk_limits=[MockRiskLimits(True)],
            parameters=Parameters(
                max_number_of_recent_candlesticks=3,
            ),
        )
        self.bull_flag_strategy._order_event.connect(self.on_order)
        self.bull_flag_strategy._opportunity_event.connect(self.on_opportunity)

    def on_order(self, sender: str, order: Order):
        self.orders.append(order)

    def on_opportunity(self, sender: str, opportunity: BullFlagOpportunity):
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
        )

    @staticmethod
    def create_mock_trade(price: float = 1.0):
        return Trade(
            trade_id=0,
            sequence_number=0,
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=MarketSide.BUY,
            price=price,
            quantity=1.0,
            transaction_time=BullFlagStrategyTest.create_mock_timestamp(),
        )

    async def test_on_candlestick(self):
        # Arrange

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[0]
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[1]
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy._order_event.has_receivers_for(ANY)
        )
        self.assertEqual(0, len(self.orders))
        self.assertEqual(1, len(self.opportunities))

    async def test_on_candlestick_wrong_order(self):
        # Assert
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[1]
        )
        with self.assertRaises(AssertionError) as context:
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[0]
            )

        self.assertRegex(
            str(context.exception),
            "^Candlesticks shall be sent in time order!",
        )

    async def test_buy_on_candlestick(self):
        # Arrange
        self.bull_flag_strategy._order_event.connect(self.on_order)
        self.bull_flag_strategy._opportunity_event.connect(self.on_opportunity)

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[0]
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender",
            Candlestick(
                BullFlagStrategyTest.create_mock_timestamp()
                + timedelta(minutes=1),
                duration_in_seconds=60,
                high=20,
                low=1,
                open=1,
                close=100,
                volume=100,
            ),
        )
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy._order_event.has_receivers_for(ANY)
        )
        self.assertEqual(1, len(self.orders))
        self.assertEqual(1, len(self.opportunities))

        # Resend the same candlesticks again should not trigger a new order
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
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

        self.bull_flag_strategy._open_positions[
            "mock_order_id"
        ] = OpenPosition(
            opportunity=BullFlagOpportunity(
                score=1.0,
                stop_loss_price=self.candlesticks[2].close + 0.01,
                profit_price=20,
            ),
            order=Order(
                client_order_id="mock_order_id",
                symbol="BTC-USD",
                order_type=OrderType.MARKET_ORDER,
                side=MarketSide.BUY,
                price=1.0,
                quantity=1.0,
                creation_time=BullFlagStrategyTest.create_mock_timestamp(),
            ),
        )
        self.assertEqual(1, len(self.bull_flag_strategy._open_positions))

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy._order_event.has_receivers_for(ANY)
        )

        sell_order = self.orders[-1]
        self.assertEqual(1, len(self.orders))
        self.assertEqual("mock_order_id", sell_order.client_order_id)
        self.assertEqual(OrderType.MARKET_ORDER, sell_order.order_type)
        self.assertEqual("BTC-USD", sell_order.symbol)
        self.assertEqual(None, sell_order.price)
        self.assertEqual(1, sell_order.quantity)
        self.assertEqual(MarketSide.SELL, sell_order.side)
        self.assertLess(
            datetime(2024, 1, 1, tzinfo=pytz.utc), sell_order.creation_time
        )
        self.assertEqual(0, len(self.bull_flag_strategy._open_positions))

    async def test_sell_for_profit_on_candlestick(self):
        # Arrange
        for i in range(0, 3):
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[i]
            )
        self.assertEqual(0, len(self.orders))

        self.bull_flag_strategy._open_positions[
            "mock_order_id"
        ] = OpenPosition(
            opportunity=BullFlagOpportunity(
                score=1.0,
                stop_loss_price=0.1,
                profit_price=self.candlesticks[2].close - 0.01,
            ),
            order=Order(
                client_order_id="mock_order_id",
                symbol="BTC-USD",
                order_type=OrderType.MARKET_ORDER,
                side=MarketSide.BUY,
                price=1.0,
                quantity=1.0,
                creation_time=BullFlagStrategyTest.create_mock_timestamp(),
            ),
        )
        self.assertEqual(1, len(self.bull_flag_strategy._open_positions))

        # Act
        self.bull_flag_strategy.on_candlestick(
            "mock_sender", self.candlesticks[2]
        )

        # Assert
        self.assertTrue(
            self.bull_flag_strategy._order_event.has_receivers_for(ANY)
        )

        sell_order = self.orders[-1]
        self.assertEqual(1, len(self.orders))
        self.assertEqual("mock_order_id", sell_order.client_order_id)
        self.assertEqual(OrderType.MARKET_ORDER, sell_order.order_type)
        self.assertEqual("BTC-USD", sell_order.symbol)
        self.assertEqual(None, sell_order.price)
        self.assertEqual(1, sell_order.quantity)
        self.assertEqual(MarketSide.SELL, sell_order.side)
        self.assertLess(
            datetime(2024, 1, 1, tzinfo=pytz.utc), sell_order.creation_time
        )
        self.assertEqual(0, len(self.bull_flag_strategy._open_positions))

    async def test_on_fill(self):
        # Act
        self.bull_flag_strategy = BullFlagStrategy(
            "ETH-USD", risk_limits=[MockRiskLimits()], parameters=Parameters()
        )
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
            self.bull_flag_strategy._order_event.has_receivers_for(ANY)
        )

    async def test_buy_order_blocked_by_risk_limits(self):
        self.bull_flag_strategy._risk_limits = [MockRiskLimits(False)]
        self.bull_flag_strategy._try_buy(
            opportunity=BullFlagOpportunity(
                score=1.0,
                stop_loss_price=0.1,
                profit_price=10,
            ),
        )
        self.assertEqual(0, len(self.orders))

    async def test_sell_order_not_blocked_by_risk_limits(self):
        self.bull_flag_strategy._risk_limits = [MockRiskLimits(False)]
        for i in range(0, 3):
            self.bull_flag_strategy.on_candlestick(
                "mock_sender", self.candlesticks[i]
            )
        self.bull_flag_strategy._open_positions[
            "mock_order_id"
        ] = OpenPosition(
            opportunity=BullFlagOpportunity(
                score=1.0,
                stop_loss_price=0.1,
                profit_price=self.candlesticks[2].close - 0.01,
            ),
            order=Order(
                client_order_id="mock_order_id",
                symbol="BTC-USD",
                order_type=OrderType.MARKET_ORDER,
                side=MarketSide.BUY,
                price=2.0,
                quantity=2.0,
                creation_time=BullFlagStrategyTest.create_mock_timestamp(),
            ),
        )
        self.bull_flag_strategy._try_close_positions()
        self.assertEqual(1, len(self.orders))
