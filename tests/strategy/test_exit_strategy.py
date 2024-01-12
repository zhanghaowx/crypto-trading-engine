import unittest
from datetime import datetime

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.market_data.core.trade import Trade
from crypto_trading_engine.strategy.exit_strategy import ExitStrategy


class ExitStrategyTest(unittest.IsolatedAsyncioTestCase):
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
    def create_mock_trade():
        return Trade(
            trade_id=0,
            sequence_number=0,
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=MarketSide.BUY,
            price=1.0,
            quantity=1.0,
            transaction_time=ExitStrategyTest.create_mock_timestamp(),
        )

    async def test_on_candlestick(self):
        # Arrange
        candlestick = Candlestick(
            ExitStrategyTest.create_mock_timestamp(), duration_in_seconds=1
        )
        # Act
        exit_strategy = ExitStrategy()
        exit_strategy.on_candlestick("mock_sender", candlestick)
        # Assert
        self.assertFalse(exit_strategy.order_event.receivers)

    async def test_on_tob(self):
        # Arrange
        # Act
        exit_strategy = ExitStrategy()
        exit_strategy.on_tob()
        # Assert
        self.assertFalse(exit_strategy.order_event.receivers)

    async def test_on_fill(self):
        # Arrange
        trade = ExitStrategyTest.create_mock_trade()
        # Act
        exit_strategy = ExitStrategy()
        exit_strategy.on_fill("mock_sender", trade)
        # Assert
        self.assertFalse(exit_strategy.order_event.receivers)
