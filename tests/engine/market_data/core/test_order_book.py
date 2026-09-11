import unittest
from datetime import datetime

from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)


class TestOrderBook(unittest.TestCase):
    def setUp(self):
        self.order_book = OrderBook("BTC/USD")
        self.exchange_time = datetime(2024, 1, 1, 12, 0, 0)

    def update(self, bids, asks, is_snapshot=False):
        return BookUpdate(
            symbol="BTC/USD",
            bids=[PriceLevel(price, quantity) for price, quantity in bids],
            asks=[PriceLevel(price, quantity) for price, quantity in asks],
            is_snapshot=is_snapshot,
            exchange_time=self.exchange_time,
        )

    def apply_snapshot(self):
        self.order_book.apply(
            self.update(
                bids=[(99.0, 2.0), (100.0, 1.0), (98.0, 3.0)],
                asks=[(102.0, 4.0), (101.0, 5.0)],
                is_snapshot=True,
            )
        )

    def test_empty_book(self):
        self.assertIsNone(self.order_book.best_bid())
        self.assertIsNone(self.order_book.best_ask())
        self.assertIsNone(self.order_book.bbo())
        self.assertEqual([], self.order_book.bids(10))
        self.assertEqual([], self.order_book.asks(10))
        self.assertIsNone(self.order_book.exchange_time)

    def test_snapshot_orders_both_sides(self):
        self.apply_snapshot()

        self.assertEqual(
            [
                PriceLevel(100.0, 1.0),
                PriceLevel(99.0, 2.0),
                PriceLevel(98.0, 3.0),
            ],
            self.order_book.bids(10),
        )
        self.assertEqual(
            [PriceLevel(101.0, 5.0), PriceLevel(102.0, 4.0)],
            self.order_book.asks(10),
        )
        self.assertEqual(PriceLevel(100.0, 1.0), self.order_book.best_bid())
        self.assertEqual(PriceLevel(101.0, 5.0), self.order_book.best_ask())
        self.assertEqual(self.exchange_time, self.order_book.exchange_time)

    def test_bbo(self):
        self.apply_snapshot()

        bbo = self.order_book.bbo()
        assert bbo is not None
        self.assertEqual("BTC/USD", bbo.symbol)
        self.assertEqual(100.0, bbo.bid_price)
        self.assertEqual(1.0, bbo.bid_quantity)
        self.assertEqual(101.0, bbo.ask_price)
        self.assertEqual(5.0, bbo.ask_quantity)

    def test_bbo_needs_both_sides(self):
        self.order_book.apply(self.update(bids=[(100.0, 1.0)], asks=[]))
        self.assertIsNone(self.order_book.bbo())

        self.order_book.apply(self.update(bids=[], asks=[(101.0, 1.0)]))
        self.assertIsNotNone(self.order_book.bbo())

    def test_depth_limits_and_rejects_non_positive(self):
        self.apply_snapshot()

        self.assertEqual(
            [PriceLevel(100.0, 1.0), PriceLevel(99.0, 2.0)],
            self.order_book.bids(2),
        )
        self.assertEqual([PriceLevel(101.0, 5.0)], self.order_book.asks(1))
        self.assertEqual([], self.order_book.bids(0))
        self.assertEqual([], self.order_book.asks(-1))

    def test_update_replaces_quantity_at_a_price(self):
        self.apply_snapshot()

        self.order_book.apply(
            self.update(bids=[(99.0, 7.0)], asks=[(101.0, 8.0)])
        )

        self.assertEqual(PriceLevel(99.0, 7.0), self.order_book.bids(10)[1])
        self.assertEqual(PriceLevel(101.0, 8.0), self.order_book.best_ask())

    def test_update_inserts_a_new_level_in_price_order(self):
        self.apply_snapshot()

        self.order_book.apply(
            self.update(bids=[(99.5, 6.0)], asks=[(101.5, 6.0)])
        )

        self.assertEqual(
            [100.0, 99.5, 99.0, 98.0],
            [level.price for level in self.order_book.bids(10)],
        )
        self.assertEqual(
            [101.0, 101.5, 102.0],
            [level.price for level in self.order_book.asks(10)],
        )

    def test_zero_quantity_removes_a_level(self):
        self.apply_snapshot()

        self.order_book.apply(
            self.update(bids=[(100.0, 0.0)], asks=[(101.0, 0.0)])
        )

        self.assertEqual(PriceLevel(99.0, 2.0), self.order_book.best_bid())
        self.assertEqual(PriceLevel(102.0, 4.0), self.order_book.best_ask())

    def test_zero_quantity_at_an_unknown_price_is_ignored(self):
        self.apply_snapshot()

        self.order_book.apply(
            self.update(bids=[(50.0, 0.0)], asks=[(150.0, 0.0)])
        )

        self.assertEqual(3, len(self.order_book.bids(10)))
        self.assertEqual(2, len(self.order_book.asks(10)))

    def test_snapshot_replaces_the_previous_book(self):
        self.apply_snapshot()

        self.order_book.apply(
            self.update(
                bids=[(90.0, 1.0)], asks=[(91.0, 1.0)], is_snapshot=True
            )
        )

        self.assertEqual([PriceLevel(90.0, 1.0)], self.order_book.bids(10))
        self.assertEqual([PriceLevel(91.0, 1.0)], self.order_book.asks(10))

    def test_clear(self):
        self.apply_snapshot()

        self.order_book.clear()

        self.assertEqual([], self.order_book.bids(10))
        self.assertEqual([], self.order_book.asks(10))

    def test_reads_do_not_expose_internal_state(self):
        self.apply_snapshot()

        self.order_book.bids(10).clear()
        self.order_book.asks(10).clear()

        self.assertEqual(3, len(self.order_book.bids(10)))
        self.assertEqual(2, len(self.order_book.asks(10)))


class TestDepthLimitedOrderBook(unittest.TestCase):
    """
    A venue publishing only the top levels does not always say when one
    falls out of that window, so the book has to trim itself.
    """

    def setUp(self):
        self.order_book = OrderBook("BTC/USD", depth=2)

    def update(self, bids, asks, is_snapshot=False):
        return BookUpdate(
            symbol="BTC/USD",
            bids=[PriceLevel(price, quantity) for price, quantity in bids],
            asks=[PriceLevel(price, quantity) for price, quantity in asks],
            is_snapshot=is_snapshot,
            exchange_time=datetime(2024, 1, 1, 12, 0, 0),
        )

    def test_depth_must_be_positive(self):
        with self.assertRaises(AssertionError):
            OrderBook("BTC/USD", depth=0)

    def test_a_snapshot_is_trimmed_to_depth(self):
        self.order_book.apply(
            self.update(
                bids=[(100.0, 1.0), (99.0, 1.0), (98.0, 1.0)],
                asks=[(101.0, 1.0), (102.0, 1.0), (103.0, 1.0)],
                is_snapshot=True,
            )
        )

        self.assertEqual(
            [100.0, 99.0],
            [level.price for level in self.order_book.bids(10)],
        )
        self.assertEqual(
            [101.0, 102.0],
            [level.price for level in self.order_book.asks(10)],
        )

    def test_a_level_pushed_out_of_the_window_does_not_linger(self):
        self.order_book.apply(
            self.update(
                bids=[(100.0, 1.0), (99.0, 1.0)],
                asks=[(101.0, 1.0), (102.0, 1.0)],
                is_snapshot=True,
            )
        )

        # A new touch on each side, with no delete for what it displaces.
        self.order_book.apply(
            self.update(bids=[(100.5, 2.0)], asks=[(100.8, 2.0)])
        )

        self.assertEqual(
            [100.5, 100.0],
            [level.price for level in self.order_book.bids(10)],
        )
        self.assertEqual(
            [100.8, 101.0],
            [level.price for level in self.order_book.asks(10)],
        )

    def test_an_unlimited_book_keeps_every_level(self):
        order_book = OrderBook("BTC/USD")

        order_book.apply(
            self.update(
                bids=[(100.0, 1.0), (99.0, 1.0), (98.0, 1.0)],
                asks=[(101.0, 1.0), (102.0, 1.0), (103.0, 1.0)],
                is_snapshot=True,
            )
        )

        self.assertEqual(3, len(order_book.bids(10)))
        self.assertEqual(3, len(order_book.asks(10)))
