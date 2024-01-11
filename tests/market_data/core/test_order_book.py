import unittest

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.order_book import (
    OrderBook,
)


class TestOrderBook(unittest.TestCase):
    def setUp(self):
        self.order_book = OrderBook()

    def test_add_buy_order(self):
        self.order_book.add_bid(100, 5)
        self.assertEqual(MarketSide.BUY, self.order_book.bids.side)
        self.assertEqual(1, len(self.order_book.bids.levels))
        self.assertEqual({100: 5}, self.order_book.bids.levels)
        self.assertEqual(5, self.order_book.bids.total_volume)

        self.order_book.add_bid(101, 10)
        self.assertEqual(2, len(self.order_book.bids.levels))
        self.assertEqual({100: 5, 101: 10}, self.order_book.bids.levels)
        self.assertEqual(15, self.order_book.bids.total_volume)

        self.order_book.add_bid(100, 1)
        self.assertEqual(2, len(self.order_book.bids.levels))
        self.assertEqual({100: 6, 101: 10}, self.order_book.bids.levels)
        self.assertEqual(16, self.order_book.bids.total_volume)

    def test_add_sell_order(self):
        self.order_book.add_ask(101, 10)
        self.assertEqual(MarketSide.SELL, self.order_book.asks.side)
        self.assertEqual(1, len(self.order_book.asks.levels))
        self.assertEqual({101: 10}, self.order_book.asks.levels)
        self.assertEqual(10, self.order_book.asks.total_volume)

        self.order_book.add_ask(102, 15)
        self.assertEqual(2, len(self.order_book.asks.levels))
        self.assertEqual({101: 10, 102: 15}, self.order_book.asks.levels)
        self.assertEqual(25, self.order_book.asks.total_volume)

        self.order_book.add_ask(101, 1)
        self.assertEqual(2, len(self.order_book.asks.levels))
        self.assertEqual({101: 11, 102: 15}, self.order_book.asks.levels)
        self.assertEqual(26, self.order_book.asks.total_volume)


if __name__ == "__main__":
    unittest.main()
