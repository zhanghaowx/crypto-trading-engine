from pathlib import Path

from streamlit.testing.v1 import AppTest

from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS
from jolteon.engine.core.parameter.parameter_specification import definitions
from jolteon.engine.core.parameter.parameter_store import (
    ParameterStore,
    override_of,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)

QUOTE_SIZE = "param.MarketMakingParameters.quote_size"
BOOK_DEPTH = "param.MarketMakingParameters.book_depth"


def _script():
    from jolteon.app.app_pages import engine_parameters

    engine_parameters.render()


def _page(params_db_path, missing_db_path) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["params_db_path"] = params_db_path
    at.session_state["db_path"] = missing_db_path
    return at


def test_renders_a_widget_for_every_declared_parameter(
    params_db_path, missing_db_path
):
    """
    The page is built from the catalog, so a parameter added to the
    engine has to appear here without anyone editing this page. If it
    cannot be rendered, that fails here rather than going unnoticed.
    """
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    kinds = (at.number_input, at.checkbox, at.selectbox, at.text_input)
    rendered = {widget.key for kind in kinds for widget in kind}
    expected = {
        f"param.{group.__name__}.{definition.name}"
        for group in GROUPS
        for definition in definitions(group)
    }
    assert expected == rendered & expected


def test_seeds_each_widget_from_its_declared_default(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    assert at.number_input(key=QUOTE_SIZE).value == 0.0005
    assert at.number_input(key=BOOK_DEPTH).value == 10


def test_takes_its_bounds_from_the_declaration(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    quote_size = at.number_input(key=QUOTE_SIZE)
    declared = {d.name: d for d in definitions(MarketMakingParameters)}
    assert quote_size.min == declared["quote_size"].minimum
    assert quote_size.max == declared["quote_size"].maximum
    assert quote_size.step == declared["quote_size"].step
    assert quote_size.help == declared["quote_size"].description


def test_an_edit_reaches_no_file_until_it_is_pushed(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

    assert not at.exception
    assert not Path(params_db_path).exists()
    assert ParameterStore(params_db_path).read() == []


def test_an_edit_shows_what_it_would_change(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()

    assert not at.exception
    assert "Push 1 change" in at.button[0].label


def test_pushing_writes_every_staged_change(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.number_input(key=BOOK_DEPTH).set_value(4).run()
    at.button[0].click().run()

    assert not at.exception
    stored = {
        o.field_name: o.value for o in ParameterStore(params_db_path).read()
    }
    assert stored == {"quote_size": 0.02, "book_depth": 4}


def test_a_pushed_int_stays_an_int(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=BOOK_DEPTH).set_value(4).run()
    at.button[0].click().run()

    stored = ParameterStore(params_db_path).read()
    assert isinstance(stored[0].value, int)
    assert stored[0].symbol == ALL_SYMBOLS


def test_pushing_clears_what_was_staged(params_db_path, missing_db_path):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["_staged_parameters"] == {}
    assert "Push 0 changes" in at.button[0].label


def test_reverting_drops_the_edit_and_writes_nothing(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[1].click().run()

    assert not at.exception
    assert at.session_state["_staged_parameters"] == {}
    assert ParameterStore(params_db_path).read() == []


def test_resetting_drops_everything_already_pushed(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[0].click().run()
    assert ParameterStore(params_db_path).read()

    at.button[2].click().run()

    assert not at.exception
    assert ParameterStore(params_db_path).read() == []


def test_a_pushed_value_comes_back_as_the_widgets_value(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()
    at.number_input(key=QUOTE_SIZE).set_value(0.02).run()
    at.button[0].click().run()

    fresh = _page(params_db_path, missing_db_path).run()
    assert fresh.number_input(key=QUOTE_SIZE).value == 0.02


def test_says_nothing_about_a_parameter_left_at_its_default(
    params_db_path, missing_db_path
):
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    assert not at.caption[1:]


def test_reports_a_stored_value_no_engine_has_read(
    params_db_path, missing_db_path
):
    """
    A pushed value with no engine behind it has to say so. Showing it in
    the widget and nothing else reads as though it were in force.
    """
    ParameterStore(params_db_path).push(
        [override_of("MarketMakingParameters", "quote_size", 0.02)]
    )
    at = _page(params_db_path, missing_db_path).run()

    assert not at.exception
    assert any(
        "no engine has reported" in caption.value for caption in at.caption
    )


class TestAStoreThePageCannotRender:
    """
    A store can hold a value no widget will take: a field's bounds may
    have been tightened after it was pushed, or something may have
    written to the store directly. The engine refuses such a value and
    keeps running, and the page has to stay up the same way - one bad
    field used to raise and take every other field down with it.
    """

    def test_a_value_above_the_maximum_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [override_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=QUOTE_SIZE).value == 10.0

    def test_a_value_below_the_minimum_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [override_of("MarketMakingParameters", "quote_size", -5.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=QUOTE_SIZE).value == 0.00001

    def test_a_value_of_the_wrong_type_does_not_break_the_page(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [override_of("MarketMakingParameters", "book_depth", "ten")]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        assert at.number_input(key=BOOK_DEPTH).value == 10

    def test_says_what_is_really_stored_and_that_it_is_refused(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [override_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        captions = " ".join(caption.value for caption in at.caption)
        assert "Stored as 99.0" in captions
        assert "refuses it" in captions
        # Its declared minimum is 0.00001, which str() renders as 1e-05.
        assert "Allowed: 0.00001 to 10.00000." in captions

    def test_every_other_field_still_renders(
        self, params_db_path, missing_db_path
    ):
        ParameterStore(params_db_path).push(
            [override_of("MarketMakingParameters", "quote_size", 99.0)]
        )
        at = _page(params_db_path, missing_db_path).run()

        assert not at.exception
        expected = sum(len(definitions(group)) for group in GROUPS)
        kinds = (at.number_input, at.checkbox, at.selectbox, at.text_input)
        assert sum(len(kind) for kind in kinds) == expected

    def test_it_is_not_quietly_corrected_on_the_users_behalf(
        self, params_db_path, missing_db_path
    ):
        """
        Showing a clamped value must not stage or push one. The bad value
        stays in the store until someone decides what it should be.
        """
        store = ParameterStore(params_db_path)
        store.push([override_of("MarketMakingParameters", "quote_size", 99.0)])
        at = _page(params_db_path, missing_db_path).run()

        assert at.session_state["_staged_parameters"] == {}
        assert store.read()[0].value == 99.0
