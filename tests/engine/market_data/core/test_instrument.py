import unittest

from jolteon.engine.market_data.core.instrument import InstrumentSpec

# The limits Kraken states for these pairs, as read from its instrument
# channel. Kept as real values because the point of every assertion below
# is what the venue actually accepts.
BTC = InstrumentSpec(
    symbol="BTC/USD",
    base="BTC",
    quote="USD",
    price_precision=1,
    qty_precision=8,
    price_increment=0.1,
    qty_min=0.00005,
    cost_min=0.5,
)
ETH = InstrumentSpec(
    symbol="ETH/USD",
    base="ETH",
    quote="USD",
    price_precision=2,
    qty_precision=8,
    price_increment=0.01,
    qty_min=0.001,
    cost_min=0.5,
)
SOL = InstrumentSpec(
    symbol="SOL/USD",
    base="SOL",
    quote="USD",
    price_precision=2,
    qty_precision=8,
    price_increment=0.01,
    qty_min=0.06,
    cost_min=0.5,
)


class TestRoundingAPrice(unittest.TestCase):
    def test_rounds_to_the_venues_increment(self):
        self.assertEqual(77300.0, BTC.round_price(77300.04))
        self.assertEqual(77300.1, BTC.round_price(77300.06))

    def test_keeps_a_price_already_on_the_increment(self):
        self.assertEqual(2513.46, ETH.round_price(2513.46))

    def test_leaves_no_float_dust_behind(self):
        """
        Dividing by a decimal increment does not come back clean, and
        Kraken reads the extra places as a price it did not quote.
        """
        self.assertEqual(0.07, SOL.round_price(0.0712))
        self.assertEqual("0.07", str(SOL.round_price(0.0712)))

    def test_an_unstated_increment_leaves_the_price_alone(self):
        spec = InstrumentSpec(symbol="ETH/USD")
        self.assertEqual(2513.456789, spec.round_price(2513.456789))


class TestRejectingAnUnsendableOrder(unittest.TestCase):
    def test_accepts_a_size_that_clears_both_limits(self):
        self.assertIsNone(BTC.rejects(0.0005, 77300.0))
        self.assertIsNone(ETH.rejects(0.01, 2513.0))

    def test_names_the_minimum_order_size_it_broke(self):
        """
        The engine's own default quote size is a tenth of what ETH
        accepts, which is the whole reason a BTC-tuned session placed no
        orders at all when it was pointed at ETH.
        """
        reason = ETH.rejects(0.0005, 2513.0)
        self.assertIn("0.001", reason)
        self.assertIn("ETH/USD", reason)

    def test_names_the_minimum_notional_it_broke(self):
        reason = SOL.rejects(0.1, 1.0)
        self.assertIn("notional", reason)
        self.assertIn("0.5", reason)

    def test_an_unconstrained_symbol_accepts_anything(self):
        """
        A replay publishes no instrument channel, so it has to quote the
        sizes it was configured with rather than refuse every one.
        """
        spec = InstrumentSpec(symbol="ETH/USD")
        self.assertIsNone(spec.rejects(0.0000001, 0.01))
