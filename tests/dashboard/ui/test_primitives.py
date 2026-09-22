from jolteon.dashboard.ui.primitives import slug


def test_slug_keeps_only_what_a_css_class_can_carry():
    assert slug("Orders & PnL") == "orders-pnl"
    assert slug("BTC/USD") == "btc-usd"
