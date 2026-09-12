import unittest
from dataclasses import dataclass

from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.parameter.parameter_specification import parameter


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


class TestFeeSchedule(unittest.TestCase):
    def setUp(self):
        self.fees = FlatFeeSchedule()

    def test_charges_each_rate_against_the_notional(self):
        self.assertAlmostEqual(0.2, self.fees.maker_fee(100.0, 2.0))
        self.assertAlmostEqual(0.4, self.fees.taker_fee(100.0, 2.0))

    def test_a_venue_must_say_what_it_charges(self):
        with self.assertRaises(TypeError):
            FeeSchedule()  # type: ignore[abstract]
