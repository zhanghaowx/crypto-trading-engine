import unittest
from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_service import (
    ParameterValues,
    StaticParameterService,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class QuotingParameters(ParameterGroup):
    quote_size: float = parameter(0.0005, minimum=0.0, maximum=1.0)
    max_inventory: float = parameter(0.01, minimum=0.0)


@dataclass(frozen=True)
class SkewParameters(ParameterGroup):
    scale: float = parameter(1.0, minimum=0.0)


class TestStaticParameterService(unittest.TestCase):
    def test_returns_declared_defaults_when_nothing_was_given(self):
        service = StaticParameterService()
        self.assertEqual(0.0005, service.get(QuotingParameters).quote_size)
        self.assertEqual(1.0, service.get(SkewParameters).scale)

    def test_an_explicit_group_wins_over_its_defaults(self):
        service = StaticParameterService(QuotingParameters(quote_size=0.01))
        self.assertEqual(0.01, service.get(QuotingParameters).quote_size)

    def test_an_unlisted_group_still_resolves_to_its_defaults(self):
        service = StaticParameterService(QuotingParameters(quote_size=0.01))
        self.assertEqual(1.0, service.get(SkewParameters).scale)

    def test_the_same_group_instance_comes_back_every_time(self):
        service = StaticParameterService()
        self.assertIs(service.get(SkewParameters), service.get(SkewParameters))

    def test_rejects_a_value_outside_its_declared_bounds(self):
        with self.assertRaises(AssertionError) as caught:
            StaticParameterService(QuotingParameters(quote_size=2.0))
        self.assertIn("QuotingParameters.quote_size", str(caught.exception))
        self.assertIn("at most 1.0", str(caught.exception))

    def test_values_reads_two_groups_at_one_revision(self):
        service = StaticParameterService(QuotingParameters(max_inventory=0.5))
        values = service.values()
        self.assertEqual(0.5, values.get(QuotingParameters).max_inventory)
        self.assertEqual(1.0, values.get(SkewParameters).scale)


class TestParameterValues(unittest.TestCase):
    def test_prefers_a_symbols_own_values_over_the_defaults(self):
        values = ParameterValues(
            revision=3,
            defaults={QuotingParameters: QuotingParameters()},
            by_symbol={
                "BTC/USD": {QuotingParameters: QuotingParameters(0.02, 0.4)}
            },
        )
        self.assertEqual(
            0.02, values.get(QuotingParameters, "BTC/USD").quote_size
        )
        self.assertEqual(0.0005, values.get(QuotingParameters).quote_size)

    def test_reading_a_group_records_the_revision_it_was_read_at(self):
        values = ParameterValues(revision=7, defaults={}, by_symbol={})
        self.assertEqual({}, values.observed)

        values.get(QuotingParameters)
        self.assertEqual({QuotingParameters: 7}, values.observed)

    def test_a_group_nobody_reads_is_never_observed(self):
        values = ParameterValues(revision=7, defaults={}, by_symbol={})
        values.get(QuotingParameters)
        self.assertNotIn(SkewParameters, values.observed)

    def test_observations_carry_forward_into_the_next_revision(self):
        first = ParameterValues(revision=7, defaults={}, by_symbol={})
        first.get(QuotingParameters)

        second = ParameterValues(
            revision=8, defaults={}, by_symbol={}, observed=first.observed
        )
        self.assertEqual(7, second.observed[QuotingParameters])

        second.get(QuotingParameters)
        self.assertEqual(8, second.observed[QuotingParameters])
