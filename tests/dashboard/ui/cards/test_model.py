from jolteon.dashboard.ui.cards.model import card_key


def test_card_key_is_derived_from_the_cards_own_id():
    assert card_key("fair-price-signals") == "card-fair-price-signals"


def test_a_bare_card_has_no_title_row_to_carry_chrome_on():
    import pytest

    from jolteon.dashboard.ui.cards import Card

    for extra in (
        {"actions": lambda: None},
        {"details": lambda: None},
        {"accent": "red"},
    ):
        with pytest.raises(ValueError, match="bare"):
            Card("summary", "Summary", "", lambda: None, frame="bare", **extra)
