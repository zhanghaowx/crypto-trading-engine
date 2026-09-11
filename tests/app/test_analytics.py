import pandas as pd
import pytest

from jolteon.app.analytics import (
    HORIZONS,
    avg_fair_price_movement,
    classify_inventory_bucket,
    compute_edge,
    compute_fill_edge,
    compute_markout,
    compute_net_markout,
    fair_price_movement,
    fill_quality_by_side,
    inventory_bucket_stats,
    signed_cash_flow,
    usd_to_bps,
)


def _fill(side, fill_price, fair_price_at_fill=None, **horizon_prices):
    row = {
        "side": side,
        "fill_price": fill_price,
        "fair_price_at_fill": fair_price_at_fill,
    }
    row.update({f"fair_price_{horizon}": None for horizon in HORIZONS})
    row.update(horizon_prices)
    return pd.DataFrame([row])


def _fills(*rows):
    """A fills table from `(side, fill_price, fair_price_at_fill, fee,
    fair_price_1s)` tuples. The other horizons are left unset (NaN), the
    same as an unbackfilled fill in the real table."""
    return pd.DataFrame(
        [
            {
                "side": row[0],
                "fill_price": row[1],
                "fair_price_at_fill": row[2],
                "fee": row[3],
                **{f"fair_price_{horizon}": None for horizon in HORIZONS},
                "fair_price_1s": row[4],
            }
            for row in rows
        ]
    )


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


def test_fill_edge_scales_by_quantity_and_subtracts_the_fee():
    fills = _fill("BUY", 95.0, fair_price_at_fill=100.0)
    fills["fill_qty"] = 2.0
    fills["fee"] = 0.5
    assert compute_fill_edge(fills).iloc[0] == pytest.approx(9.5)


def test_fill_edge_turns_negative_when_the_fee_outweighs_the_edge():
    fills = _fill("SELL", 100.1, fair_price_at_fill=100.0)
    fills["fill_qty"] = 1.0
    fills["fee"] = 0.5
    assert compute_fill_edge(fills).iloc[0] == pytest.approx(-0.4)


def test_buying_pays_cash_out_and_selling_brings_cash_in():
    fills = pd.DataFrame(
        {
            "side": ["BUY", "SELL"],
            "fill_price": [100.0, 200.0],
            "fill_qty": [2.0, 0.5],
        }
    )
    assert list(signed_cash_flow(fills)) == pytest.approx([-200.0, 100.0])


def test_fair_price_movement_is_signed_and_side_independent():
    up = _fill("SELL", 100.0, fair_price_at_fill=100.0, fair_price_1s=103.0)
    down = _fill("BUY", 100.0, fair_price_at_fill=100.0, fair_price_1s=97.0)
    assert fair_price_movement(up, "1s").iloc[0] == pytest.approx(3.0)
    assert fair_price_movement(down, "1s").iloc[0] == pytest.approx(-3.0)


def test_avg_fair_price_movement_averages_across_fills():
    fills = pd.concat(
        [
            _fill("BUY", 100.0, fair_price_at_fill=100.0, fair_price_1s=103.0),
            _fill("BUY", 100.0, fair_price_at_fill=100.0, fair_price_1s=97.0),
        ],
        ignore_index=True,
    )
    assert avg_fair_price_movement(fills)["1s"] == pytest.approx(0.0)


def test_fill_quality_by_side_separates_buy_and_sell():
    fills = _fills(
        ("BUY", 100.0, 101.0, 0.1, 103.0),
        ("BUY", 100.0, 99.0, 0.2, 97.0),
        ("SELL", 110.0, 108.0, 0.05, 105.0),
    )

    by_side = fill_quality_by_side(fills)

    assert by_side.loc["BUY", "fill_count"] == 2
    assert by_side.loc["BUY", "avg_edge"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_fee"] == pytest.approx(0.15)
    assert by_side.loc["BUY", "avg_markout_1s"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_net_markout_1s"] == pytest.approx(-0.15)

    assert by_side.loc["SELL", "fill_count"] == 1
    assert by_side.loc["SELL", "avg_edge"] == pytest.approx(2.0)
    assert by_side.loc["SELL", "avg_fee"] == pytest.approx(0.05)
    assert by_side.loc["SELL", "avg_markout_1s"] == pytest.approx(5.0)
    assert by_side.loc["SELL", "avg_net_markout_1s"] == pytest.approx(4.95)


def test_classify_inventory_bucket_matches_default_boundaries():
    inventory = pd.Series([-0.6, -0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5, 0.6])
    buckets = classify_inventory_bucket(inventory)
    assert list(buckets.astype(str)) == [
        "Strongly short",
        "Strongly short",
        "Moderately short",
        "Moderately short",
        "Near neutral",
        "Near neutral",
        "Moderately long",
        "Moderately long",
        "Strongly long",
    ]


def test_classify_inventory_bucket_uses_custom_boundaries():
    boundaries = (("Short", -1.0), ("Long", float("inf")))
    buckets = classify_inventory_bucket(
        pd.Series([-2.0, 0.0, 2.0]), boundaries
    )
    assert list(buckets.astype(str)) == ["Short", "Long", "Long"]


def _fill_with_inventory(side, inventory_before, fee, fair_price_1s):
    row = {
        "side": side,
        "fill_price": 100.0,
        "fill_qty": 1.0,
        "fee": fee,
        "inventory_before": inventory_before,
        "fair_price_at_fill": 100.0,
        **{f"fair_price_{h}": None for h in HORIZONS},
        "fair_price_1s": fair_price_1s,
    }
    return row


def test_inventory_bucket_stats_splits_by_bucket():
    fills = pd.DataFrame(
        [
            _fill_with_inventory("BUY", -0.6, 0.1, 103.0),
            _fill_with_inventory("SELL", 0.0, 0.2, 98.0),
        ]
    )

    stats = inventory_bucket_stats(fills)

    assert stats.loc["Strongly short", "fill_count"] == 1
    assert stats.loc["Strongly short", "buy_count"] == 1
    assert stats.loc["Strongly short", "sell_count"] == 0
    assert stats.loc["Strongly short", "avg_markout_1s"] == pytest.approx(3.0)
    assert stats.loc["Strongly short", "net_cash_flow"] == pytest.approx(
        -100.1
    )

    assert stats.loc["Near neutral", "fill_count"] == 1
    assert stats.loc["Near neutral", "avg_markout_1s"] == pytest.approx(2.0)
    assert stats.loc["Near neutral", "net_cash_flow"] == pytest.approx(99.8)

    assert "Strongly long" not in stats.index
