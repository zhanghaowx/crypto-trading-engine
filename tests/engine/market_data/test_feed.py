import unittest
from unittest.mock import MagicMock

from jolteon.engine.market_data.core.order_book import OrderBook
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed
from jolteon.engine.market_data.historical_feed import HistoricalFeed
from jolteon.engine.market_data.kraken.public_feed import PublicFeed


class TestMarketDataFeed(unittest.TestCase):
    def test_a_feed_must_declare_what_it_publishes(self):
        class IncompleteFeed(IMarketDataFeed):
            pass

        with self.assertRaises(TypeError):
            IncompleteFeed("incomplete", 10)

    def test_replay_publishes_market_trades_only(self):
        feed = HistoricalFeed(MagicMock())

        self.assertEqual(frozenset({Channel.MARKET_TRADE}), feed.channels)

    def test_kraken_publishes_trades_and_the_touch(self):
        feed = PublicFeed()

        self.assertIn(Channel.MARKET_TRADE, feed.channels)
        self.assertIn(Channel.TICKER, feed.channels)

    def test_every_feed_carries_its_own_events(self):
        self.assertIsNotNone(PublicFeed().events.market_trade)
        self.assertIsNotNone(HistoricalFeed(MagicMock()).events.market_trade)


class TestEvents(unittest.TestCase):
    def test_feeds_share_one_order_book_signal(self):
        self.assertIs(
            PublicFeed().events.order_book,
            HistoricalFeed(MagicMock()).events.order_book,
        )

    def test_raw_books_are_not_recorded(self):
        self.assertFalse(OrderBook("BTC/USD").RECORDED)
