from jolteon.dashboard.ui.cards.model import Card
from jolteon.dashboard.ui.cards.style import (
    accent_rule,
    card_grid_rule,
    cards_rule,
    surface_rule,
)


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


def test_cards_rule_names_every_card():
    rule = cards_rule(
        [
            Card("health", "Health", ":material/monitor_heart:", lambda: None),
            Card("errors", "Errors", ":material/error:", lambda: None),
        ]
    )

    assert ":is(.st-key-card-health, .st-key-card-errors)" in rule
    assert "transition: box-shadow" in rule


def test_cards_rule_scopes_descendants_to_every_card_not_just_the_last():
    """Regression test: a bare comma list binds a descendant part to only
    the final selector (`.a, .b desc` means `.a` OR `.b desc`), so every
    card but the last took the expander rules on itself and the page
    laid out sideways. `:is()` distributes them over all of them."""
    rule = cards_rule(
        [
            Card("health", "Health", ":material/monitor_heart:", lambda: None),
            Card("errors", "Errors", ":material/error:", lambda: None),
        ]
    )

    scope = ":is(.st-key-card-health, .st-key-card-errors)"
    assert f"{scope} [class*=" in rule
    assert rule.count(scope) > 1
    # Never a bare comma list in front of a descendant part.
    assert ".st-key-card-errors [data-testid" not in rule


def test_cards_rule_is_empty_without_cards():
    assert cards_rule([]) == ""


def test_accent_rule_stripes_the_named_card_in_the_theme_color():
    rule = accent_rule("card-risk-limits", "red")

    assert ".st-key-card-risk-limits {" in rule
    assert "border-left: 5px solid #DC2626" in rule


def test_accent_rule_is_empty_for_a_card_with_no_accent():
    assert accent_rule("card-risk-limits", None) == ""
