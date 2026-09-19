from streamlit.testing.v1 import AppTest

from jolteon.app.card import (
    Card,
    accent_rule,
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


def detailed_card_script():
    import streamlit as st

    from jolteon.app.card import Card, render_cards

    render_cards(
        [
            Card(
                "Market Data",
                ":material/show_chart:",
                lambda: st.write("md"),
                details=lambda: st.write("every tick"),
            )
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

    assert [b.label for b in at.button if b.label] == ["Download"]


def test_every_card_carries_its_own_chrome():
    at = AppTest.from_function(cards_script).run()

    keys = [b.key for b in at.button]
    for title in ("card-market-data", "card-orders-pnl"):
        assert f"{title}-details" in keys
        assert f"{title}-collapse" in keys
        assert f"{title}-hide" in keys


def test_a_card_collapses_to_its_title_and_expands_again():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-collapse").click().run()

    assert not at.exception
    assert [s.value for s in at.subheader] == ["Market Data", "Orders & PnL"]
    assert "md" not in [m.value for m in at.markdown]
    assert "pnl" in [m.value for m in at.markdown]

    at.button(key="card-market-data-collapse").click().run()

    assert "md" in [m.value for m in at.markdown]


def test_collapsing_one_card_leaves_the_others_open():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-orders-pnl-collapse").click().run()

    assert not at.exception
    assert "md" in [m.value for m in at.markdown]
    assert "pnl" not in [m.value for m in at.markdown]


def test_the_details_icon_opens_the_card_in_a_modal():
    at = AppTest.from_function(cards_script).run()

    assert not at.get("dialog")

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    assert at.get("dialog")
    # The card's content moves into the modal rather than being drawn in
    # both places at once.
    assert [m.value for m in at.markdown].count("md") == 1


def test_the_modal_stays_open_across_a_refresh():
    """The pages cards render on rerun on a timer. A modal opened straight
    from the button's return value would close again on the first refresh
    after it was opened."""
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-details").click().run()
    at.run()

    assert not at.exception
    assert at.get("dialog")


def test_a_card_with_details_shows_those_instead_of_its_content():
    at = AppTest.from_function(detailed_card_script).run()

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    values = [m.value for m in at.markdown]
    assert "every tick" in values
    assert "md" not in values


def test_the_close_icon_hides_a_card_and_offers_it_back():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-hide").click().run()

    assert not at.exception
    assert [s.value for s in at.subheader] == ["Orders & PnL"]
    assert at.button(key="card-unhide").label == "Show Market Data"

    at.button(key="card-unhide").click().run()

    assert [s.value for s in at.subheader] == ["Market Data", "Orders & PnL"]


def test_a_hidden_card_stays_hidden_across_a_refresh():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-hide").click().run()
    at.run()

    assert not at.exception
    assert [s.value for s in at.subheader] == ["Orders & PnL"]


def test_nothing_is_offered_back_while_every_card_is_showing():
    at = AppTest.from_function(cards_script).run()

    assert not at.exception
    assert "card-unhide" not in [b.key for b in at.button]


def test_hiding_a_card_closes_the_modal_it_had_open():
    """Nothing draws a hidden card, so a modal left open on one could
    never be dismissed - its card is no longer there to render it."""
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-details").click().run()
    at.button(key="card-market-data-hide").click().run()

    assert not at.exception
    assert not at.get("dialog")


def accented_cards_script():
    import streamlit as st

    from jolteon.app.card import Card, render_cards

    render_cards(
        [
            Card(
                "Market Data",
                ":material/show_chart:",
                lambda: st.write("md"),
                accent="blue",
            ),
            Card(
                "Risk Limits",
                ":material/earthquake:",
                lambda: st.write("risk"),
                accent=lambda: st.session_state.get("risk_accent"),
            ),
        ]
    )


def keyed_card_script():
    import streamlit as st

    from jolteon.app.card import Card, render_cards

    def body() -> None:
        st.write("md")
        st.button("Refresh", key="market-data-refresh")

    render_cards([Card("Market Data", ":material/show_chart:", body)])


def test_a_card_whose_content_keys_a_widget_still_opens_in_a_modal():
    """Regression test: the modal draws the card's own content, so a card
    that keys anything inside it - the risk gauges, the page through
    recent fills - was asked for that key twice in the same run, which
    Streamlit refuses."""
    at = AppTest.from_function(keyed_card_script).run()

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    assert at.get("dialog")
    # Drawn in the modal rather than on the page, not in both.
    assert [m.value for m in at.markdown].count("md") == 1
    assert len([b for b in at.button if b.key == "market-data-refresh"]) == 1


def test_accent_rule_stripes_the_named_card_in_the_theme_color():
    rule = accent_rule("card-risk-limits", "red")

    assert ".st-key-card-risk-limits {" in rule
    assert "border-left: 5px solid #DC2626" in rule


def test_accent_rule_is_empty_for_a_card_with_no_accent():
    assert accent_rule("card-risk-limits", None) == ""


def test_a_cards_accent_reaches_the_page():
    at = AppTest.from_function(accented_cards_script).run()

    assert not at.exception
    rules = [h.body for h in at.get("html")]
    assert any(
        ".st-key-card-market-data {" in rule and "#3E8FD0" in rule
        for rule in rules
    )


def test_an_accent_given_as_a_function_follows_what_it_reports_on():
    at = AppTest.from_function(accented_cards_script)
    at.session_state["risk_accent"] = "green"
    at.run()

    assert "#16A34A" in " ".join(h.body for h in at.get("html"))

    at.session_state["risk_accent"] = "red"
    at.run()

    assert "#DC2626" in " ".join(h.body for h in at.get("html"))


def test_a_card_without_an_accent_emits_no_rule_for_one():
    at = AppTest.from_function(accented_cards_script).run()

    assert not at.exception
    assert not any(
        ".st-key-card-risk-limits {" in h.body for h in at.get("html")
    )
