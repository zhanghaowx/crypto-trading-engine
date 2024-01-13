import unittest
from datetime import datetime, timedelta

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit
from crypto_trading_engine.strategy.bull_flag.bull_flag_strategy import (
    BullFlagStrategy,
)


class MockRiskLimits(IRiskLimit):
    def __init__(self, always_allow: bool = False):
        self.always_allow = always_allow

    def can_send(self):
        return self.always_allow

    def do_send(self):
        pass


class BullFlagStrategyTest(unittest.IsolatedAsyncioTestCase):
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
        candlestick1 = Candlestick(
            BullFlagStrategyTest.create_mock_timestamp(), duration_in_seconds=1
        )
        candlestick1.low = 1
        candlestick1.high = 10
        candlestick1.open = 1
        candlestick1.close = 10
        candlestick1.volume = 100

        candlestick2 = Candlestick(
            BullFlagStrategyTest.create_mock_timestamp()
            + timedelta(minutes=1),
            duration_in_seconds=1,
        )
        candlestick2.low = 1
        candlestick2.high = 10
        candlestick2.open = 1
        candlestick2.close = 10
        candlestick2.volume = 100

        # Act
        bull_flag_strategy = BullFlagStrategy(
            "ETH-USD",
            risk_limits=[],
            max_number_of_recent_candlesticks=2,
            min_return_of_extreme_bullish_candlesticks=0.00001,
            min_return_of_active_candlesticks=0.00001,
        )
        bull_flag_strategy.on_candlestick("mock_sender", candlestick1)
        bull_flag_strategy.on_candlestick("mock_sender", candlestick2)

        # Assert
        self.assertFalse(bull_flag_strategy.order_event.receivers)

    async def test_on_fill(self):
        # Act
        bull_flag_strategy = BullFlagStrategy(
            "ETH-USD", risk_limits=[MockRiskLimits()]
        )
        bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.0)
        )
        bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.1)
        )
        bull_flag_strategy.on_fill(
            "mock_sender", BullFlagStrategyTest.create_mock_trade(1.2)
        )

        # Assert
        self.assertFalse(bull_flag_strategy.order_event.receivers)
