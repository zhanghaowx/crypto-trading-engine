from streamlit.testing.v1 import AppTest

from jolteon.app.card import (
    Card,
    card_grid_rule,
    card_key,
    cards_rule,
    surface_rule,
)


def card_grid_script():
    import streamlit as st

    from jolteon.app.card import card_grid

    for item in card_grid(["a", "b", "c"], key="demo-cards", columns=2):
        st.write(item)


def card_grid_empty_script():
    import streamlit as st

    from jolteon.app.card import card_grid

    st.write(list(card_grid([], key="demo-cards", columns=2)))


def cards_script():
    import streamlit as st

    from jolteon.app.card import Card, render_cards

    render_cards(
        [
            Card(
                "Market Data", ":material/show_chart:", lambda: st.write("md")
            ),
            Card(
                "Orders & PnL",
                ":material/currency_bitcoin:",
                lambda: st.write("pnl"),
                actions=lambda: st.button("Download"),
            ),
        ]
    )


def test_card_grid_renders_every_item_in_a_bordered_container():
    at = AppTest.from_function(card_grid_script).run()

    assert not at.exception
    assert [m.value for m in at.markdown] == ["a", "b", "c"]


def test_card_grid_yields_nothing_for_an_empty_list():
    at = AppTest.from_function(card_grid_empty_script).run()

    assert not at.exception
    assert at.json[0].value == "[]"


def test_card_grid_rule_caps_the_columns_and_their_minimum_width():
    rule = card_grid_rule("cards", columns=3, min_width=240)

    assert ".st-key-cards {" in rule
    assert "columns: 3 240px" in rule


def test_card_grid_rule_keeps_a_card_from_splitting_across_columns():
    rule = card_grid_rule("cards", columns=3, min_width=240)

    assert ".st-key-cards > * {" in rule
    assert "break-inside: avoid" in rule


def test_surface_rule_scopes_itself_to_the_keys_given():
    rule = surface_rule(["one", "two"])

    assert ".st-key-one, .st-key-two {" in rule
    assert rule.startswith("<style>")


def test_surface_rule_is_empty_when_there_are_no_cards():
    """
    An empty selector would leave `{ ... }` on its own, which is not a
    rule the browser can apply to anything, so a page with no cards has
    to emit no style block at all.
    """
    assert surface_rule([]) == ""


def test_card_key_is_derived_from_the_title():
    assert card_key("Fair Price Signals") == "card-fair-price-signals"


def test_cards_rule_names_every_card():
    rule = cards_rule(
        [
            Card("Health", ":material/monitor_heart:", lambda: None),
            Card("Errors", ":material/error:", lambda: None),
        ]
    )

    assert ".st-key-card-health, .st-key-card-errors {" in rule
    assert "transition: height" in rule


def test_cards_rule_is_empty_without_cards():
    assert cards_rule([]) == ""


def test_every_card_renders_under_its_own_title():
    at = AppTest.from_function(cards_script).run()

    assert not at.exception
    assert [s.value for s in at.subheader] == ["Market Data", "Orders & PnL"]
    assert [m.value for m in at.markdown if m.value in ("md", "pnl")] == [
        "md",
        "pnl",
    ]


def test_a_cards_own_action_renders_beside_its_title():
    at = AppTest.from_function(cards_script).run()

    assert [b.label for b in at.button] == ["Download"]
