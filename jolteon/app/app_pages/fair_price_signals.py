"""Fair Price Signals: how well each registered fair price adjustment has
predicted the market's actual forward move, so far this session - the
evidence a weight decision gets made from."""

import pandas as pd
import streamlit as st

from jolteon.app.analytics import HORIZONS
from jolteon.app.components import styled_table, warn_if_no_db
from jolteon.app.data import read_table
from jolteon.app.signal_evaluation import evaluate_adjustments

_HORIZON_PHRASES = {
    "100ms": "100 milliseconds",
    "1s": "1 second",
    "5s": "5 seconds",
    "30s": "30 seconds",
}

_HORIZON_COLUMNS = [f"+{horizon}" for horizon in HORIZONS]

# Overlapping, autocorrelated tick pairs make the effective sample
# far smaller than the raw count, so this floor is deliberately high.
_MIN_SAMPLES = 30

_COLLECTING = "Collecting…"

_SLOPE_HELP = (
    r"$$\beta = \frac{\operatorname{Cov}(s,\ r)}{\operatorname{Var}(s)}$$"
    "\n\n"
    r"where $s$ is the adjustment's own value and $r$ is the market's"
    r" actual forward move. Both are in price units, so $\beta$ reads"
    r" directly as the weight the adjustment should carry."
)

_CORRELATION_HELP = (
    r"$$\rho = \frac{\operatorname{Cov}(s,\ r)}{\sigma_s\ \sigma_r}$$"
    "\n\n"
    r"where $s$ is the adjustment's own value and $r$ is the market's"
    r" actual forward move. Dividing by both spreads instead of only"
    r" the adjustment's keeps $\rho$ between -1 and +1."
)


def _fmt_ratio(value: float) -> str:
    if pd.isna(value):
        return _COLLECTING
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.2f}"


def _pivot(evaluation: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """`evaluation`'s long (adjustment, horizon) rows as one row per
    adjustment, one column per horizon, with any figure resting on fewer
    than `_MIN_SAMPLES` pairs blanked out."""
    trusted = evaluation[value_column].where(evaluation["n"] >= _MIN_SAMPLES)
    pivoted = evaluation.assign(**{value_column: trusted}).pivot(
        index="adjustment", columns="horizon", values=value_column
    )
    pivoted = pivoted.reindex(columns=list(HORIZONS))
    pivoted.columns = _HORIZON_COLUMNS
    return pivoted.reset_index().rename(columns={"adjustment": "Adjustment"})


def _render_slope(evaluation: pd.DataFrame) -> None:
    st.markdown("**Calibration (β)**", help=_SLOPE_HELP)
    table = _pivot(evaluation, "slope")
    column_config = {
        column: st.column_config.NumberColumn(
            help="Regression slope of the market's actual forward move "
            f"{_HORIZON_PHRASES[horizon]} later against this adjustment's "
            "own value at the time - the suggested weight. 1.0 means "
            "correctly scaled, a smaller magnitude means the adjustment "
            "is oversized, and a negative sign means it points the "
            "wrong way."
        )
        for column, horizon in zip(_HORIZON_COLUMNS, HORIZONS)
    }
    styled = styled_table(table, _HORIZON_COLUMNS, _fmt_ratio)
    st.dataframe(
        styled, hide_index=True, width="stretch", column_config=column_config
    )


def _render_correlation(evaluation: pd.DataFrame) -> None:
    st.markdown("**Reliability (ρ)**", help=_CORRELATION_HELP)
    table = _pivot(evaluation, "correlation")
    column_config = {
        column: st.column_config.NumberColumn(
            help="Correlation between this adjustment's value and the "
            f"market's actual forward move {_HORIZON_PHRASES[horizon]} "
            "later. Near zero means the slope is likely noise regardless "
            "of its size; closer to +/-1 means it reflects a real "
            "relationship."
        )
        for column, horizon in zip(_HORIZON_COLUMNS, HORIZONS)
    }
    styled = styled_table(table, _HORIZON_COLUMNS, _fmt_ratio)
    st.dataframe(
        styled, hide_index=True, width="stretch", column_config=column_config
    )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    adjustments = read_table(db_path, "fair_price_adjustment")
    if adjustments.empty:
        st.info("No fair price adjustments recorded yet.")
        return

    fair_price = read_table(db_path, "fair_price")
    evaluation = evaluate_adjustments(adjustments, fair_price)
    if evaluation.empty:
        st.info("Waiting for fair price data to evaluate against.")
        return

    if (evaluation["n"] < _MIN_SAMPLES).all():
        st.info(
            "Collecting data - no horizon has enough samples to evaluate "
            "against yet."
        )
        return

    _render_slope(evaluation)
    st.divider()
    _render_correlation(evaluation)
