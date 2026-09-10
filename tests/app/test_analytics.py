import pandas as pd
import pytest

from jolteon.app.analytics import (
    compute_edge,
    compute_markout,
    compute_net_markout,
    usd_to_bps,
)


def _fill(side, fill_price, fair_price_at_fill=None, **horizon_prices):
    row = {
        "side": side,
        "fill_price": fill_price,
        "fair_price_at_fill": fair_price_at_fill,
    }
    row.update(horizon_prices)
    return pd.DataFrame([row])


def test_buy_favorable_markout_is_positive():
    fills = _fill("BUY", 100.0, fair_price_1s=105.0)
    assert compute_markout(fills, "1s").iloc[0] == pytest.approx(5.0)


def test_buy_adverse_markout_is_negative():
    fills = _fill("BUY", 100.0, fair_price_1s=95.0)
    assert compute_markout(fills, "1s").iloc[0] == pytest.approx(-5.0)


def test_sell_favorable_markout_is_positive():
    fills = _fill("SELL", 100.0, fair_price_1s=95.0)
    assert compute_markout(fills, "1s").iloc[0] == pytest.approx(5.0)


def test_sell_adverse_markout_is_negative():
    fills = _fill("SELL", 100.0, fair_price_1s=105.0)
    assert compute_markout(fills, "1s").iloc[0] == pytest.approx(-5.0)


def test_zero_markout_when_price_unchanged():
    fills = _fill("BUY", 100.0, fair_price_1s=100.0)
    assert compute_markout(fills, "1s").iloc[0] == pytest.approx(0.0)


def test_missing_future_fair_price_is_nan():
    fills = _fill("BUY", 100.0, fair_price_1s=None)
    assert pd.isna(compute_markout(fills, "1s").iloc[0])


def test_net_markout_subtracts_the_fee():
    markout = pd.Series([5.0])
    fee = pd.Series([0.2])
    assert compute_net_markout(markout, fee).iloc[0] == pytest.approx(4.8)


def test_usd_to_bps_conversion():
    usd = pd.Series([1.0])
    execution_price = pd.Series([100.0])
    assert usd_to_bps(usd, execution_price).iloc[0] == pytest.approx(100.0)


def test_buy_edge_is_fair_minus_execution_price():
    fills = _fill("BUY", 95.0, fair_price_at_fill=100.0)
    assert compute_edge(fills).iloc[0] == pytest.approx(5.0)


def test_sell_edge_is_execution_price_minus_fair():
    fills = _fill("SELL", 105.0, fair_price_at_fill=100.0)
    assert compute_edge(fills).iloc[0] == pytest.approx(5.0)
