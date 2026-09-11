import unittest

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.quote_offset import (
    FeeAwareQuoteOffsetService,
    IQuoteOffsetService,
    QuoteOffset,
    StaticQuoteOffsetService,
)


def snapshot(bid: float = 99.0, ask: float = 101.0) -> BookSnapshot:
    return BookSnapshot(
        bbo=BBO(
            symbol="BTC/USD",
            bid_price=bid,
            bid_quantity=1.0,
            ask_price=ask,
            ask_quantity=1.0,
        )
    )


class TestStaticQuoteOffsetService(unittest.TestCase):
    def test_quotes_the_same_half_spread_on_both_sides(self):
        offset = StaticQuoteOffsetService(half_spread=25.0).calculate(
            snapshot()
        )

        self.assertEqual(QuoteOffset(bid=25.0, ask=25.0), offset)

    def test_rejects_a_non_positive_half_spread(self):
        with self.assertRaises(AssertionError):
            StaticQuoteOffsetService(half_spread=0.0)


class TestFeeAwareQuoteOffsetService(unittest.TestCase):
    def setUp(self):
        self.fees = FeeSchedule(maker_rate=0.001, taker_rate=0.002)

    def test_charges_the_edge_on_top_of_the_maker_fee(self):
        service = FeeAwareQuoteOffsetService(edge=5.0, fees=self.fees)

        offset = service.calculate(snapshot(bid=1000.0, ask=1200.0))

        self.assertAlmostEqual(6.0, offset.bid)
        self.assertAlmostEqual(6.2, offset.ask)

    def test_widens_as_the_price_rises(self):
        service = FeeAwareQuoteOffsetService(edge=5.0, fees=self.fees)

        cheap = service.calculate(snapshot(bid=1000.0, ask=1000.0))
        rich = service.calculate(snapshot(bid=100000.0, ask=100000.0))

        self.assertAlmostEqual(6.0, cheap.bid)
        self.assertAlmostEqual(105.0, rich.bid)

    def test_never_quotes_inside_the_fee(self):
        service = FeeAwareQuoteOffsetService(edge=0.01, fees=self.fees)

        offset = service.calculate(snapshot(bid=50000.0, ask=50000.0))

        self.assertGreater(offset.bid, self.fees.maker_fee(50000.0, 1.0))

    def test_rejects_a_non_positive_edge(self):
        with self.assertRaises(AssertionError):
            FeeAwareQuoteOffsetService(edge=0.0, fees=self.fees)


class TestIQuoteOffsetService(unittest.TestCase):
    def test_publishes_every_offset_it_calculates(self):
        seen = []
        service = StaticQuoteOffsetService(half_spread=25.0)

        def on_quote_offset(_, quote_offset_update):
            seen.append(quote_offset_update)

        service.quote_offset_event.connect(on_quote_offset)
        self.addCleanup(service.quote_offset_event.disconnect, on_quote_offset)

        service.calculate(snapshot())

        self.assertEqual(1, len(seen))
        self.assertEqual("BTC/USD", seen[0].symbol)
        self.assertEqual("StaticQuoteOffsetService", seen[0].service)
        self.assertEqual(25.0, seen[0].bid_offset)
        self.assertEqual(25.0, seen[0].ask_offset)

    def test_rejects_an_offset_that_would_cross_the_fair_price(self):
        class _Crossing(IQuoteOffsetService):
            def _calculate(self, context: BookSnapshot) -> QuoteOffset:
                return QuoteOffset(bid=-1.0, ask=1.0)

        with self.assertRaises(AssertionError):
            _Crossing().calculate(snapshot())
