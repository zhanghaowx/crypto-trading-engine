import unittest
from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
    parameter,
)


@dataclass(frozen=True)
class SampleParameters(ParameterGroup):
    size: float = parameter(
        0.5,
        minimum=0.0,
        maximum=1.0,
        step=0.1,
        number_format="%.1f",
        unit="BTC",
        description="How big each quote is.",
    )
    depth: int = parameter(10, minimum=1, maximum=100)
    undeclared: bool = False


class TestParameterSpecification(unittest.TestCase):
    def setUp(self):
        self.by_name = {d.name: d for d in definitions(SampleParameters)}

    def test_records_what_was_declared(self):
        size = self.by_name["size"]
        self.assertEqual(0.0, size.minimum)
        self.assertEqual(1.0, size.maximum)
        self.assertEqual(0.1, size.step)
        self.assertEqual("%.1f", size.number_format)
        self.assertEqual("BTC", size.unit)
        self.assertEqual("How big each quote is.", size.description)

    def test_fills_in_name_type_and_default_from_the_field(self):
        size = self.by_name["size"]
        self.assertEqual("size", size.name)
        self.assertEqual(float, size.value_type)
        self.assertEqual(0.5, size.default)
        self.assertEqual(int, self.by_name["depth"].value_type)

    def test_keeps_declared_order(self):
        self.assertEqual(
            ["size", "depth", "undeclared"],
            [d.name for d in definitions(SampleParameters)],
        )

    def test_a_plainly_assigned_field_still_yields_a_definition(self):
        undeclared = self.by_name["undeclared"]
        self.assertEqual(bool, undeclared.value_type)
        self.assertFalse(undeclared.default)
        self.assertIsNone(undeclared.minimum)

    def test_declared_defaults_construct_the_group(self):
        self.assertEqual(0.5, SampleParameters().size)
        self.assertEqual(10, SampleParameters().depth)
