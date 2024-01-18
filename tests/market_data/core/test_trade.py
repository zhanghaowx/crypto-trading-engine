import unittest
from datetime import datetime
from jolteon.core.side import MarketSide
from jolteon.market_data.core.trade import Trade


class TestTrade(unittest.TestCase):
    def test_trade_equality(self):
        now = datetime.now()

        # Create two identical trades
        trade1 = Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC-USD",
            maker_order_id="order1",
            taker_order_id="order2",
            side=MarketSide.BUY,
            price=100.0,
            quantity=1.5,
            transaction_time=now,
        )

        trade2 = Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC-USD",
            maker_order_id="order1",
            taker_order_id="order2",
            side=MarketSide.BUY,
            price=100.0,
            quantity=1.5,
            transaction_time=now,
        )

        # Check that the trades are equal
        self.assertEqual(trade1, trade2)

    def test_trade_inequality(self):
        # Create two different trades
        trade1 = Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC-USD",
            maker_order_id="order1",
            taker_order_id="order2",
            side=MarketSide.BUY,
            price=100.0,
            quantity=1.5,
            transaction_time=datetime.now(),
        )

        trade2 = Trade(
            trade_id=2,
            client_order_id="",
            symbol="ETH-USD",
            maker_order_id="order3",
            taker_order_id="order4",
            side=MarketSide.SELL,
            price=200.0,
            quantity=2.0,
            transaction_time=datetime.now(),
        )

        # Check that the trades are not equal
        self.assertNotEqual(trade1, trade2)

    def test_trade_hash(self):
        # Create a trade
        trade = Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC-USD",
            maker_order_id="order1",
            taker_order_id="order2",
            side=MarketSide.BUY,
            price=100.0,
            quantity=1.5,
            transaction_time=datetime.now(),
        )

        # Calculate the hash
        expected_hash = hash(
            (
                1,
                "",
                "BTC-USD",
                "order1",
                "order2",
                MarketSide.BUY,
                100.0,
                1.5,
                trade.transaction_time,
            )
        )

        # Check that the calculated hash matches the expected hash
        self.assertEqual(hash(trade), expected_hash)

    def test_trade_market_side(self):
        market_side = MarketSide.BUY

        # Create a trade
        trade = Trade(
            trade_id=1,
            client_order_id="",
            symbol="BTC-USD",
            maker_order_id="order1",
            taker_order_id="order2",
            side=market_side,
            price=100.0,
            quantity=1.5,
            transaction_time=datetime.now(),
        )

        self.assertIsInstance(trade.side, MarketSide)
