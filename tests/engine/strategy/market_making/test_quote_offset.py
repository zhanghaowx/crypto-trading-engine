import unittest
from dataclasses import dataclass

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
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


@dataclass(frozen=True)
class FlatFeeSchedule(FeeSchedule):
    maker: float = parameter(0.001, minimum=0.0, maximum=0.1)
    taker: float = parameter(0.002, minimum=0.0, maximum=0.1)

    @property
    def maker_rate(self) -> float:
        return self.maker

    @property
    def taker_rate(self) -> float:
        return self.taker


class TestFeeAwareQuoteOffsetService(unittest.TestCase):
    def setUp(self):
        self.fees = FlatFeeSchedule()

    def service(
        self, *groups: ParameterGroup, edge: float | None = None
    ) -> FeeAwareQuoteOffsetService:
        return FeeAwareQuoteOffsetService(
            fee_schedule=FlatFeeSchedule,
            edge=edge,
            parameter_service=StaticParameterService(*groups),
        )

    def test_charges_the_edge_on_top_of_the_maker_fee(self):
        offset = self.service(edge=5.0).calculate(
            snapshot(bid=1000.0, ask=1200.0)
        )

        self.assertAlmostEqual(6.0, offset.bid)
        self.assertAlmostEqual(6.2, offset.ask)

    def test_widens_as_the_price_rises(self):
        service = self.service(edge=5.0)

        cheap = service.calculate(snapshot(bid=1000.0, ask=1000.0))
        rich = service.calculate(snapshot(bid=100000.0, ask=100000.0))

        self.assertAlmostEqual(6.0, cheap.bid)
        self.assertAlmostEqual(105.0, rich.bid)

    def test_never_quotes_inside_the_fee(self):
        offset = self.service(edge=0.01).calculate(
            snapshot(bid=50000.0, ask=50000.0)
        )

        self.assertGreater(offset.bid, self.fees.maker_fee(50000.0, 1.0))

    def test_rejects_a_non_positive_edge(self):
        with self.assertRaises(AssertionError):
            self.service(edge=0.0)

    def test_no_edge_takes_it_from_the_parameter_service(self):
        service = self.service(QuoteOffsetParameters(edge=2.0))

        offset = service.calculate(snapshot(bid=1000.0, ask=1200.0))

        self.assertAlmostEqual(3.0, offset.bid)
        self.assertAlmostEqual(3.2, offset.ask)

    def test_follows_a_retuned_fee_schedule(self):
        """
        The schedule is read on every quote, so an account that reaches a
        cheaper tier mid session stops charging for fees it no longer pays.
        """
        service = self.service(FlatFeeSchedule(maker=0.0, taker=0.0), edge=2.0)

        self.assertAlmostEqual(
            2.0, service.calculate(snapshot(bid=1000.0, ask=1000.0)).bid
        )

    def test_falls_back_to_the_declared_defaults(self):
        offset = self.service().calculate(snapshot(bid=1000.0, ask=1000.0))

        declared = QuoteOffsetParameters().edge + FlatFeeSchedule().maker_fee(
            1000.0, 1.0
        )
        self.assertAlmostEqual(declared, offset.bid)


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
