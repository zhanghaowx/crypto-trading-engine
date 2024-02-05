import unittest
from datetime import datetime

from blinker import ANY

from jolteon.core.event.signal import signal
from jolteon.core.side import MarketSide
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.trade import Trade
from jolteon.strategy.bootstrap.bootstrap_strategy import (
    BootstrapStrategy,
)


class BootstrapStrategyTest(unittest.IsolatedAsyncioTestCase):
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
            client_order_id="",
            symbol="ES",
            maker_order_id="1",
            taker_order_id="2",
            side=MarketSide.BUY,
            price=1.0,
            fee=0.0,
            quantity=2.0,
            transaction_time=BootstrapStrategyTest.create_mock_timestamp(),
        )

    async def test_on_candlestick(self):
        # Arrange
        candlestick = Candlestick(
            BootstrapStrategyTest.create_mock_timestamp(),
            duration_in_seconds=1,
        )
        candlestick.open = 1.0
        candlestick.close = 2.0
        candlestick.high = 4.0
        candlestick.low = 0.5

        # Act
        boostrap_strategy = BootstrapStrategy()
        boostrap_strategy.connect()

        # Assert
        self.assertTrue(
            boostrap_strategy.on_candlestick
            in signal("calculated_candlestick_feed").receivers_for(ANY)
        )

        # Test sending a signal won't cause crash
        signal("calculated_candlestick_feed").send(
            "mock_sender", candlestick=candlestick
        )

    async def test_on_fill(self):
        # Arrange
        trade = BootstrapStrategyTest.create_mock_trade()

        # Act
        boostrap_strategy = BootstrapStrategy()
        boostrap_strategy.connect()

        # Assert
        self.assertTrue(
            boostrap_strategy.on_fill
            in signal("order_fill").receivers_for(ANY)
        )

        # Test sending a signal won't cause crash
        signal("order_fill").send("mock_sender", trade=trade)
