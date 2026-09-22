from jolteon.dashboard.ui.cards.model import card_key


def test_card_key_is_derived_from_the_cards_own_id():
    assert card_key("fair-price-signals") == "card-fair-price-signals"
