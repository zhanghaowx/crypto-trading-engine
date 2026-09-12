import unittest
from dataclasses import MISSING, dataclass, fields
from unittest.mock import patch

from jolteon.engine.core.parameter import parameter_catalog
from jolteon.engine.core.parameter.parameter_catalog import (
    GROUPS,
    group_by_name,
    validate,
)
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    definitions,
    parameter,
)


@dataclass(frozen=True)
class BoundedParameters(ParameterGroup):
    ratio: float = parameter(0.5, minimum=0.0, maximum=1.0)


class TestCatalogedGroupsAreWellFormed(unittest.TestCase):
    """
    The one guard that keeps every group renderable as the catalog grows:
    the Parameters page builds its widgets from what these declare, so a
    field missing a default or a type fails here rather than on the page.
    """

    def test_no_two_groups_share_a_name(self):
        self.assertEqual(len(GROUPS), len(group_by_name()))

    def test_every_field_has_a_default(self):
        for group in GROUPS:
            for declared in fields(group):
                with self.subTest(group=group.__name__, field=declared.name):
                    self.assertIsNot(MISSING, declared.default)

    def test_every_field_declares_a_real_type(self):
        for group in GROUPS:
            for definition in definitions(group):
                with self.subTest(group=group.__name__, field=definition.name):
                    self.assertIsInstance(definition.value_type, type)

    def test_every_default_sits_within_its_own_bounds(self):
        for group in GROUPS:
            for definition in definitions(group):
                with self.subTest(group=group.__name__, field=definition.name):
                    if definition.minimum is not None:
                        self.assertGreaterEqual(
                            definition.default, definition.minimum
                        )
                    if definition.maximum is not None:
                        self.assertLessEqual(
                            definition.default, definition.maximum
                        )

    def test_every_group_constructs_from_its_defaults(self):
        for group in GROUPS:
            with self.subTest(group=group.__name__):
                self.assertIsInstance(group(), group)


class TestValidate(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(
            parameter_catalog, "GROUPS", (BoundedParameters,)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_says_nothing_about_values_within_bounds(self):
        values = StaticParameterService(BoundedParameters(0.5)).values()
        self.assertEqual([], validate(values))

    def test_reports_the_field_and_the_bound_it_broke(self):
        values = StaticParameterService().values()
        object.__setattr__(values.get(BoundedParameters), "ratio", 4.0)

        problems = validate(values)
        self.assertEqual(1, len(problems))
        self.assertIn("BoundedParameters.ratio", problems[0])
        self.assertIn("at most 1.0", problems[0])
