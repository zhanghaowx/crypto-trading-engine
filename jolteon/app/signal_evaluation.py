"""How well each fair price adjustment predicted the market's actual
forward move, at each markout horizon.

Operates on the `fair_price_adjustment` and `fair_price` tables (read via
`jolteon.app.data.read_table`) - nothing here writes back to the
database. A candidate adjustment can run in production at zero weight,
fully recorded, and this module is what turns that recording into a
weight worth trying.
"""

import pandas as pd

from jolteon.app.analytics import HORIZONS

MID_MODEL = "MidPriceFairPriceModel"

_HORIZON_SECONDS = {"100ms": 0.1, "1s": 1.0, "5s": 5.0, "30s": 30.0}

TOTAL_ADJUSTMENT_COLUMN = "total_adjustment"
TOTAL_ADJUSTMENT_LABEL = "Total"


def _adjustment_columns(adjustments: pd.DataFrame) -> list[str]:
    return [c for c in adjustments.columns if c.startswith("adjustments.")]


def _display_name(column: str) -> str:
    if column == TOTAL_ADJUSTMENT_COLUMN:
        return TOTAL_ADJUSTMENT_LABEL
    return column.removeprefix("adjustments.")


def _forward_mid(
    adjustments: pd.DataFrame, fair_price: pd.DataFrame, horizon_seconds: float
) -> pd.Series:
    """The next base-model mid recorded at or after `horizon_seconds` past
    each adjustment row's own timestamp, matched per symbol - NaN where no
    such mid has been recorded yet (the session hasn't run that far)."""
    mid = fair_price[fair_price["model"] == MID_MODEL].copy()
    mid["mid"] = (mid["bid_fair_price"] + mid["ask_fair_price"]) / 2
    mid = mid[["symbol", "timestamp", "mid"]].sort_values("timestamp")

    left = adjustments[["symbol", "timestamp"]].reset_index()
    left["target_timestamp"] = left["timestamp"] + horizon_seconds
    left = left.sort_values("target_timestamp")

    merged = pd.merge_asof(
        left,
        mid,
        left_on="target_timestamp",
        right_on="timestamp",
        by="symbol",
        direction="forward",
    )
    return merged.set_index("index")["mid"].reindex(adjustments.index)


def _slope_and_correlation(
    signal: pd.Series, forward_return: pd.Series
) -> tuple[float, float, int]:
    """Regression slope and Pearson correlation of `forward_return` against
    `signal`, dropping any row where either side is unavailable. The slope
    is in the same price units as `signal` itself, so it reads directly as
    calibration: 1.0 means correctly scaled, a smaller magnitude means the
    adjustment is oversized, and a negative sign means it points the wrong
    way."""
    paired = pd.DataFrame(
        {"signal": signal, "forward_return": forward_return}
    ).dropna()
    signal_variance = paired["signal"].var()
    forward_variance = paired["forward_return"].var()
    if len(paired) < 2 or not signal_variance or not forward_variance:
        return float("nan"), float("nan"), len(paired)

    slope = paired["signal"].cov(paired["forward_return"]) / signal_variance
    correlation = paired["signal"].corr(paired["forward_return"])
    return float(slope), float(correlation), len(paired)


def evaluate_adjustments(
    adjustments: pd.DataFrame, fair_price: pd.DataFrame
) -> pd.DataFrame:
    """One row per (adjustment, horizon) - including `total_adjustment`,
    labeled "Total" - each with the sample count behind it, the
    calibration slope, and the correlation. Empty if either table is
    empty."""
    if adjustments.empty or fair_price.empty:
        return pd.DataFrame(
            columns=["adjustment", "horizon", "n", "slope", "correlation"]
        )

    signal_columns = [
        *_adjustment_columns(adjustments),
        TOTAL_ADJUSTMENT_COLUMN,
    ]
    rows = []
    for horizon in HORIZONS:
        forward_mid = _forward_mid(
            adjustments, fair_price, _HORIZON_SECONDS[horizon]
        )
        forward_return = forward_mid - adjustments["base_fair_price"]
        for column in signal_columns:
            slope, correlation, n = _slope_and_correlation(
                adjustments[column], forward_return
            )
            rows.append(
                {
                    "adjustment": _display_name(column),
                    "horizon": horizon,
                    "n": n,
                    "slope": slope,
                    "correlation": correlation,
                }
            )
    return pd.DataFrame(rows)
