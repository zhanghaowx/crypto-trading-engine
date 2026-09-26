import pytest

from jolteon.dashboard.read_models.strategy import strategy_name


@pytest.mark.parametrize(
    ("recorded", "name"),
    [
        ("MarketMakingStrategy", "Market making"),
        ("BootstrapStrategy", "Bootstrap"),
    ],
)
def test_the_strategies_the_engine_ships_have_plain_names(recorded, name):
    assert strategy_name(recorded) == name


def test_a_strategy_it_does_not_know_is_named_by_its_class():
    assert strategy_name("MeanReversionStrategy") == "Mean reversion"
    assert strategy_name("Momentum") == "Momentum"


def test_a_run_that_ran_no_strategy_has_no_name():
    assert strategy_name("") == ""
