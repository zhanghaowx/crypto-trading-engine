import unittest

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.strategy.market_making.parameters import (
    QuoteOffsetParameters,
)
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

    def test_no_half_spread_takes_the_declared_default(self):
        offset = StaticQuoteOffsetService().calculate(snapshot())

        self.assertEqual(QuoteOffsetParameters().half_spread, offset.bid)

    def test_no_half_spread_follows_a_retuned_parameter(self):
        """
        Passing one fixes it for the life of the service, so leaving it
        out is the only way a dashboard can widen a running quote.
        """
        service = StaticQuoteOffsetService(
            parameter_service=StaticParameterService(
                QuoteOffsetParameters(half_spread=12.5)
            )
        )

        self.assertEqual(
            QuoteOffset(bid=12.5, ask=12.5), service.calculate(snapshot())
        )

    def test_a_passed_half_spread_ignores_the_parameter_service(self):
        service = StaticQuoteOffsetService(
            half_spread=25.0,
            parameter_service=StaticParameterService(
                QuoteOffsetParameters(half_spread=12.5)
            ),
        )

        self.assertEqual(25.0, service.calculate(snapshot()).bid)


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

    def test_no_edge_or_fees_takes_them_from_the_parameter_service(self):
        service = FeeAwareQuoteOffsetService(
            parameter_service=StaticParameterService(
                QuoteOffsetParameters(edge=2.0),
                FeeSchedule(maker_rate=0.001, taker_rate=0.002),
            )
        )

        offset = service.calculate(snapshot(bid=1000.0, ask=1200.0))

        self.assertAlmostEqual(3.0, offset.bid)
        self.assertAlmostEqual(3.2, offset.ask)

    def test_falls_back_to_the_declared_defaults(self):
        offset = FeeAwareQuoteOffsetService().calculate(
            snapshot(bid=1000.0, ask=1000.0)
        )

        declared = QuoteOffsetParameters().edge + FeeSchedule().maker_fee(
            1000.0, 1.0
        )
        self.assertAlmostEqual(declared, offset.bid)

    def test_passed_fees_are_kept_over_a_retuned_schedule(self):
        service = FeeAwareQuoteOffsetService(
            fees=self.fees,
            parameter_service=StaticParameterService(
                QuoteOffsetParameters(edge=2.0),
                FeeSchedule(maker_rate=0.1, taker_rate=0.1),
            ),
        )

        self.assertAlmostEqual(
            3.0, service.calculate(snapshot(bid=1000.0, ask=1000.0)).bid
        )


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
