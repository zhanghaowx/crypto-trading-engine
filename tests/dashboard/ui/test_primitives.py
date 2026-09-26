from jolteon.dashboard.ui.primitives import badge_css, slug


def test_slug_keeps_only_what_a_css_class_can_carry():
    assert slug("Orders & PnL") == "orders-pnl"
    assert slug("BTC/USD") == "btc-usd"


def test_badges_are_recolored_by_the_theme_color_streamlit_wrote():
    """Streamlit tints a badge with its theme color at a tenth of its
    strength, inline; the rule that redraws a green badge has to find it
    by that tint and outrank the inline style."""
    css = badge_css()

    green = (
        '.stMarkdownBadge[style*="rgba(19, 117, 82"] {'
        " background: var(--positive-soft) !important;"
        " color: var(--positive) !important; }"
    )
    assert green in css
    assert 'rgba(182, 62, 73"] { background: var(--negative-soft)' in css
    # Orange keeps the theme's darker amber, a step past yellow.
    assert (
        'rgba(111, 67, 12"] { background: var(--warning-soft) !important;'
        " color: var(--warning-strong)"
    ) in css
    assert (
        'rgba(148, 99, 21"] { background: var(--warning-soft) !important;'
        " color: var(--warning)"
    ) in css
    assert (
        'rgba(98, 109, 124"] { background: var(--subtle) !important;'
        " color: var(--muted)"
    ) in css


def test_every_badge_leads_with_a_dot_at_the_prototypes_size():
    css = badge_css()

    assert (
        '[data-testid="stMarkdownContainer"] span.stMarkdownBadge::before'
        in css
    )
    assert "background: currentColor" in css
    assert "font-size: 11px !important" in css
    assert "%(" not in css
