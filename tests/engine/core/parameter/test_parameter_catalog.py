import unittest
from dataclasses import MISSING, dataclass, fields
from unittest.mock import patch

from jolteon.engine.core.health_monitor.parameters import HeartbeatParameters
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

    def test_the_declared_defaults_pass_their_own_validation(self):
        """
        An engine nobody has tuned runs on exactly these, so a default
        that breaks a constraint would reject every later push too.
        """
        self.assertEqual([], validate(StaticParameterService().values()))

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
        self.assertEqual("BoundedParameters", problems[0].group_name)
        self.assertEqual("ratio", problems[0].field_name)
        self.assertIn("at most 1.0", problems[0].message)


class TestConstraintsAcrossTwoGroups(unittest.TestCase):
    """
    Some constraints are about how two fields sit together and cannot be
    stated on either one, so bounds alone will not catch them.
    """

    def test_a_timeout_shorter_than_the_beat_is_refused(self):
        values = StaticParameterService(
            HeartbeatParameters(
                interval_in_seconds=10.0, timeout_in_seconds=5.0
            )
        ).values()

        problems = validate(values)
        self.assertEqual(
            ["timeout_in_seconds"], [p.field_name for p in problems]
        )
        self.assertIn("zombie", problems[0].message)

    def test_a_timeout_equal_to_the_beat_is_refused(self):
        """
        Equal leaves no room for a single missed beat, so a component
        that is alive and on time reads as a zombie.
        """
        values = StaticParameterService(
            HeartbeatParameters(
                interval_in_seconds=10.0, timeout_in_seconds=10.0
            )
        ).values()

        self.assertEqual(
            ["timeout_in_seconds"], [p.field_name for p in validate(values)]
        )

    def test_a_timeout_longer_than_the_beat_is_accepted(self):
        values = StaticParameterService(
            HeartbeatParameters(
                interval_in_seconds=10.0, timeout_in_seconds=10.5
            )
        ).values()

        self.assertEqual([], validate(values))

    def test_checking_the_pair_is_not_a_component_reading_it(self):
        """
        Validating must not look like a pickup, or a pushed value would
        report as applied before anything used it.
        """
        values = StaticParameterService().values()
        validate(values)
        self.assertNotIn(HeartbeatParameters, values.observed)
