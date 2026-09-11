import unittest
from datetime import datetime

from jolteon.engine.market_data.book_feature_recorder import (
    BookFeatureRecorder,
)
from jolteon.engine.market_data.core.events import Events
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)


class TestBookFeatureRecorder(unittest.TestCase):
    def setUp(self):
        self.recorder = BookFeatureRecorder()
        self.published = []
        self.recorder.book_features_event.connect(
            lambda sender, **kwargs: self.published.append(
                kwargs["book_features"]
            ),
            weak=False,
        )

    def book(self, bids, asks) -> OrderBook:
        order_book = OrderBook("BTC/USD")
        order_book.apply(
            BookUpdate(
                symbol="BTC/USD",
                bids=[PriceLevel(price, qty) for price, qty in bids],
                asks=[PriceLevel(price, qty) for price, qty in asks],
                is_snapshot=True,
                exchange_time=datetime(2024, 1, 1),
            )
        )
        return order_book

    def test_a_one_sided_book_records_nothing(self):
        self.recorder.on_order_book("_", self.book([(100.0, 1.0)], []))

        self.assertEqual([], self.published)

    def test_records_the_touch(self):
        self.recorder.on_order_book(
            "_", self.book([(100.0, 1.0)], [(101.0, 2.0)])
        )

        features = self.published[0]
        self.assertEqual("BTC/USD", features.symbol)
        self.assertEqual(100.0, features.bid_price)
        self.assertEqual(1.0, features.bid_quantity)
        self.assertEqual(101.0, features.ask_price)
        self.assertEqual(2.0, features.ask_quantity)

    def test_records_imbalance_at_several_depths(self):
        order_book = self.book(
            bids=[(100.0, 1.0), (99.0, 8.0)],
            asks=[(101.0, 1.0), (102.0, 2.0)],
        )

        self.recorder.on_order_book("_", order_book)

        features = self.published[0]
        self.assertEqual(0.0, features.imbalance_1)
        self.assertAlmostEqual(0.5, features.imbalance_5)
        self.assertAlmostEqual(0.5, features.imbalance_10)

    def test_records_the_price_of_sweeping_each_side(self):
        order_book = self.book(
            bids=[(100.0, 1.0), (99.0, 1.0)],
            asks=[(101.0, 3.0), (102.0, 1.0)],
        )

        self.recorder.on_order_book("_", order_book)

        features = self.published[0]
        self.assertAlmostEqual(99.5, features.depth_weighted_bid)
        self.assertAlmostEqual(101.25, features.depth_weighted_ask)

    def test_a_snapshot_is_narrow_enough_to_record(self):
        self.recorder.on_order_book(
            "_", self.book([(100.0, 1.0)], [(101.0, 2.0)])
        )

        self.assertEqual(10, len(vars(self.published[0])))

    def test_subscribes_to_the_order_book_signal(self):
        self.recorder.connect()
        events = Events()

        events.order_book.send(
            events.order_book,
            order_book=self.book([(100.0, 1.0)], [(101.0, 2.0)]),
        )

        self.assertEqual(1, len(self.published))
