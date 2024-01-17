import unittest
from datetime import datetime
from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.strategy.bull_flag.open_position import OpenPosition
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


class TestStrategyOrder(unittest.TestCase):
    def setUp(self):
        opportunity = TradeOpportunity(
            score=1.0,
            stop_loss_price=100.0,
            profit_price=200.0,
        )
        order = Order(
            client_order_id="123",
            order_type=OrderType.MARKET_ORDER,
            symbol="BTC-USD",
            side=MarketSide.BUY,
            price=100,
            quantity=1,
            creation_time=datetime(2024, 1, 1, 0, 0, 0),
        )
        self.strategy_order = OpenPosition(
            opportunity=opportunity, order=order
        )

    def test_should_close_for_loss(self):
        # Test when market_price is less than stop_loss_price
        market_price = 95
        result = self.strategy_order.should_close_for_loss(market_price)
        self.assertTrue(result)

        # Test when market_price is equal to stop_loss_price
        market_price = 100
        result = self.strategy_order.should_close_for_loss(market_price)
        self.assertFalse(result)

        # Test when market_price is greater than stop_loss_price
        market_price = 105
        result = self.strategy_order.should_close_for_loss(market_price)
        self.assertFalse(result)

    def test_should_close_for_profit(self):
        # Test when market_price is greater than profit_price
        market_price = 205
        result = self.strategy_order.should_close_for_profit(market_price)
        self.assertTrue(result)

        # Test when market_price is equal to profit_price
        market_price = 200
        result = self.strategy_order.should_close_for_profit(market_price)
        self.assertFalse(result)

        # Test when market_price is less than profit_price
        market_price = 195
        result = self.strategy_order.should_close_for_profit(market_price)
        self.assertFalse(result)
