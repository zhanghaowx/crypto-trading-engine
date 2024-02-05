import unittest
import uuid
from datetime import datetime
from random import randint

from jolteon.core.side import MarketSide
from jolteon.market_data.core.order import Order, OrderType
from jolteon.market_data.core.trade import Trade
from jolteon.strategy.bull_trend_rider.trade_record import (
    TradeRecord,
)
from jolteon.strategy.core.trade_opportunity import TradeOpportunityCore


class TestBullTrendRiderTradeRecord(unittest.TestCase):
    @staticmethod
    def create_order(market_side: MarketSide):
        return Order(
            client_order_id="123",
            order_type=OrderType.MARKET_ORDER,
            symbol="BTC-USD",
            side=market_side,
            price=100,
            quantity=1,
            creation_time=datetime(2024, 1, 1, 0, 0, 0),
        )

    @staticmethod
    def create_trade(market_side: MarketSide):
        return Trade(
            trade_id=randint(1, 1000),
            client_order_id="123",
            symbol="BTC-USD",
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=market_side,
            price=1,
            fee=0.0,
            quantity=1,
            transaction_time=datetime(2024, 1, 1, 0, 0, 0),
        )

    def setUp(self):
        opportunity = TradeOpportunityCore(
            score=1.0,
            stop_loss_price=100.0,
            profit_price=200.0,
        )

        self.round_trip = TradeRecord(
            opportunity=opportunity,
        )

    def test_constructor(self):
        with self.assertRaises(AssertionError):
            TradeRecord(
                opportunity=self.round_trip.opportunity,
                buy_order=self.create_order(MarketSide.SELL),
            )

        with self.assertRaises(AssertionError):
            TradeRecord(
                opportunity=self.round_trip.opportunity,
                sell_order=self.create_order(MarketSide.BUY),
            )

    def test_should_sell_for_loss(self):
        self.round_trip.buy_order = self.create_order(MarketSide.BUY)

        # Test when market_price is less than stop_loss_price
        market_price = 95
        result = self.round_trip.should_sell_for_loss(market_price)
        self.assertTrue(result)

        # Test when market_price is equal to stop_loss_price
        market_price = 100
        result = self.round_trip.should_sell_for_loss(market_price)
        self.assertFalse(result)

        # Test when market_price is greater than stop_loss_price
        market_price = 105
        result = self.round_trip.should_sell_for_loss(market_price)
        self.assertFalse(result)

    def test_should_sell_for_profit(self):
        self.round_trip.buy_order = self.create_order(MarketSide.BUY)

        # Test when market_price is greater than profit_price
        market_price = 205
        result = self.round_trip.should_sell_for_profit(market_price)
        self.assertTrue(result)

        # Test when market_price is equal to profit_price
        market_price = 200
        result = self.round_trip.should_sell_for_profit(market_price)
        self.assertFalse(result)

        # Test when market_price is less than profit_price
        market_price = 195
        result = self.round_trip.should_sell_for_profit(market_price)
        self.assertFalse(result)
