from pathlib import Path

from streamlit.testing.v1 import AppTest

from jolteon.engine.core.parameter.parameter_catalog import GROUPS
from jolteon.engine.core.parameter.parameter_service import ALL_SYMBOLS
from jolteon.engine.core.parameter.parameter_specification import definitions
from jolteon.engine.core.parameter.parameter_store import ParameterStore
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
