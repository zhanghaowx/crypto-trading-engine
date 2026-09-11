import math

import pandas as pd
import pytest

from jolteon.app.signal_evaluation import evaluate_adjustments


def _adjustments(*rows):
    """A fair_price_adjustment table from (timestamp, base_fair_price,
    momentum, total_adjustment) tuples, one BTC-USD row per tuple."""
    return pd.DataFrame(
        [
            {
                "symbol": "BTC-USD",
                "timestamp": row[0],
                "base_fair_price": row[1],
                "adjustments.momentum": row[2],
                "total_adjustment": row[3],
                "clamped": False,
            }
            for row in rows
        ]
    )


def _fair_price(*rows, symbol="BTC-USD", model="MidPriceFairPriceModel"):
    """A fair_price table from (timestamp, mid) tuples, one row per
    tuple, all for the same model/symbol unless overridden."""
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "model": model,
                "timestamp": row[0],
                "bid_fair_price": row[1],
                "ask_fair_price": row[1],
            }
            for row in rows
        ]
    )


def test_empty_tables_return_an_empty_frame():
    result = evaluate_adjustments(pd.DataFrame(), pd.DataFrame())

    assert result.empty
    assert list(result.columns) == [
        "adjustment",
        "horizon",
        "n",
        "slope",
        "correlation",
    ]


def test_perfectly_calibrated_signal_scores_slope_and_correlation_of_one():
    adjustments = _adjustments(
        (1000.0, 100.0, 1.0, 1.0),
        (1001.0, 100.0, -1.0, -1.0),
    )
    fair_price = _fair_price((1001.0, 101.0), (1002.0, 99.0))

    result = evaluate_adjustments(adjustments, fair_price)

    one_second = result[
        (result["horizon"] == "1s") & (result["adjustment"] == "momentum")
    ].iloc[0]
    assert one_second["n"] == 2
    assert one_second["slope"] == pytest.approx(1.0)
    assert one_second["correlation"] == pytest.approx(1.0)


def test_total_adjustment_row_is_labeled_total():
    adjustments = _adjustments(
        (1000.0, 100.0, 1.0, 1.0), (1001.0, 100.0, -1.0, -1.0)
    )
    fair_price = _fair_price((1001.0, 101.0), (1002.0, 99.0))

    result = evaluate_adjustments(adjustments, fair_price)

    assert "Total" in set(result["adjustment"])
    assert "total_adjustment" not in set(result["adjustment"])


def test_horizon_with_no_recorded_mid_yet_is_nan():
    adjustments = _adjustments(
        (1000.0, 100.0, 1.0, 1.0), (1001.0, 100.0, -1.0, -1.0)
    )
    fair_price = _fair_price((1001.0, 101.0), (1002.0, 99.0))

    result = evaluate_adjustments(adjustments, fair_price)

    thirty_second = result[
        (result["horizon"] == "30s") & (result["adjustment"] == "momentum")
    ].iloc[0]
    assert thirty_second["n"] == 0
    assert math.isnan(thirty_second["slope"])
    assert math.isnan(thirty_second["correlation"])


def test_a_different_symbols_mid_is_never_matched():
    adjustments = _adjustments((1000.0, 100.0, 1.0, 1.0))
    fair_price = _fair_price((1001.0, 101.0), symbol="ETH-USD")

    result = evaluate_adjustments(adjustments, fair_price)

    one_second = result[
        (result["horizon"] == "1s") & (result["adjustment"] == "momentum")
    ].iloc[0]
    assert one_second["n"] == 0


def test_a_constant_signal_has_no_defined_slope():
    adjustments = _adjustments(
        (1000.0, 100.0, 1.0, 1.0), (1001.0, 100.0, 1.0, 1.0)
    )
    fair_price = _fair_price((1001.0, 101.0), (1002.0, 105.0))

    result = evaluate_adjustments(adjustments, fair_price)

    one_second = result[
        (result["horizon"] == "1s") & (result["adjustment"] == "momentum")
    ].iloc[0]
    assert math.isnan(one_second["slope"])
    assert math.isnan(one_second["correlation"])
