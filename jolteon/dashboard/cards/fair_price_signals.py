"""Fair Price Signals: how well each registered fair price adjustment has
predicted the market's actual forward move, so far this session - the
evidence a weight decision gets made from."""

from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.analysis.markouts import HORIZONS
from jolteon.analysis.signals import evaluate_adjustments
from jolteon.dashboard.data.runs import read_run_table
from jolteon.dashboard.data.sqlite import recorded_through
from jolteon.dashboard.state import current_run_id
from jolteon.dashboard.ui import table
from jolteon.dashboard.ui.empty_states import warn_if_no_db
from jolteon.dashboard.ui.primitives import BadgeColor, slug

_ROWS_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "signal_rows.css"
).read_text()


# Scoring every recorded adjustment against what the price went on to do
# is the whole cost of this card, and answers the same until more of
# either is recorded. The frames go unhashed (a leading underscore);
# `through` is the key. See `recorded_through`.
@st.cache_data(show_spinner=False)
def cached_evaluation(
    _adjustments: pd.DataFrame, _fair_price: pd.DataFrame, through: tuple
) -> pd.DataFrame:
    return evaluate_adjustments(_adjustments, _fair_price)


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
    r" actual forward move. If the adjustment says the price should be a"
    r" dollar higher and it really does rise a dollar, $\beta$ is 1."
    "\n\n"
    r"Read Reliability first. $\beta$ is calculated whether or not there"
    r" is any relationship to measure, so against an unreliable"
    r" adjustment it is a confident-looking number drawn from noise."
)

_CORRELATION_HELP = (
    r"$$\rho = \frac{\operatorname{Cov}(s,\ r)}{\sigma_s\ \sigma_r}$$"
    "\n\n"
    r"where $s$ is the adjustment's own value and $r$ is the market's"
    r" actual forward move. Dividing by both spreads instead of only"
    r" the adjustment's keeps $\rho$ between -1 and +1."
    "\n\n"
    r"How consistently the adjustment and the market's next move agree."
    r" Near zero means they do not, and nothing else on this page means"
    r" anything until this is far enough from it."
)

_VERDICT_HELP = (
    "What the two figures below add up to for each adjustment, read"
    " at whichever horizon its reliability is strongest."
    "\n\n"
    "These bands are rules of thumb for deciding whether a number is"
    " worth acting on, not statistical tests."
)

# How far correlation has to sit from zero before the calibration beside
# it is worth reading at all, and then before it is worth sizing from.
_NO_SIGNAL = 0.05
_WORTH_SIZING = 0.15

_NO_USABLE_SIGNAL = "No usable signal yet"
_TOO_WEAK = "Too weak to size from"
_WRONG_WAY = "Points the wrong way"
_WORTH_A_WEIGHT = "Worth a weight"

# A signal still warming up, or too faint to use, is a normal state and
# is badged as one. Only a signal pointing the wrong way is a finding to
# act on, and it is the only verdict badged in a warning colour.
_VERDICT_COLORS: dict[str, BadgeColor] = {
    _WORTH_A_WEIGHT: "green",
    _COLLECTING: "gray",
    _NO_USABLE_SIGNAL: "gray",
    _TOO_WEAK: "gray",
    _WRONG_WAY: "orange",
}


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


def _verdict(rows: pd.DataFrame) -> str:
    """What one adjustment's figures amount to, in words a reader can act
    on, taken at the horizon where its correlation is strongest."""
    usable = rows[rows["n"] >= _MIN_SAMPLES].dropna(subset=["correlation"])
    if usable.empty:
        return _COLLECTING

    best = usable.loc[usable["correlation"].abs().idxmax()]
    strength = abs(best["correlation"])
    if strength < _NO_SIGNAL:
        return _NO_USABLE_SIGNAL
    if strength < _WORTH_SIZING:
        return _TOO_WEAK
    if best["correlation"] < 0:
        return _WRONG_WAY
    return _WORTH_A_WEIGHT


def _render_verdict(evaluation: pd.DataFrame) -> None:
    """One row per adjustment: its name, and its verdict as a badge."""
    st.markdown("**Verdict**", help=_VERDICT_HELP)
    st.html(f"<style>{_ROWS_CSS}</style>")
    for name, group in evaluation.groupby("adjustment", sort=False):
        verdict = _verdict(group)
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            key=f"signal-row-{slug(str(name))}",
        ):
            st.markdown(str(name), width="content")
            st.badge(verdict, color=_VERDICT_COLORS[verdict])


def _render_slope(evaluation: pd.DataFrame) -> None:
    st.markdown("**Calibration (β)**", help=_SLOPE_HELP)
    column_help = {
        column: (
            "Regression slope of the market's actual forward move "
            f"{_HORIZON_PHRASES[horizon]} later against this adjustment's "
            "own value at the time. 1.0 means correctly scaled, a "
            "smaller magnitude means the adjustment is oversized, and a "
            "negative sign means it points the wrong way. Worth reading "
            "only where the reliability above is far enough from zero."
        )
        for column, horizon in zip(_HORIZON_COLUMNS, HORIZONS)
    }
    table.render(
        _pivot(evaluation, "slope"),
        shaded_columns=_HORIZON_COLUMNS,
        format_fn=_fmt_ratio,
        column_help=column_help,
    )


def _render_correlation(evaluation: pd.DataFrame) -> None:
    st.markdown("**Reliability (ρ)**", help=_CORRELATION_HELP)
    column_help = {
        column: (
            "Correlation between this adjustment's value and the "
            f"market's actual forward move {_HORIZON_PHRASES[horizon]} "
            "later. Near zero means the calibration beside it is likely "
            "noise regardless of its size; closer to +/-1 means it "
            "reflects a real relationship."
        )
        for column, horizon in zip(_HORIZON_COLUMNS, HORIZONS)
    }
    table.render(
        _pivot(evaluation, "correlation"),
        shaded_columns=_HORIZON_COLUMNS,
        format_fn=_fmt_ratio,
        column_help=column_help,
    )


def _evaluation() -> pd.DataFrame | None:
    """
    Returns: How each adjustment has scored against what the price went
    on to do, or nothing at all when too little has been recorded to say
    - having already said on screen which of those it is.
    """
    if not warn_if_no_db():
        return None

    db_path = st.session_state.db_path
    run_id = current_run_id()
    adjustments = read_run_table(db_path, "fair_price_adjustment", run_id)
    if adjustments.empty:
        st.info("No fair price adjustments recorded yet.")
        return None

    fair_price = read_run_table(db_path, "fair_price", run_id)
    evaluation = cached_evaluation(
        adjustments,
        fair_price,
        (
            recorded_through(adjustments, time_column="timestamp"),
            recorded_through(fair_price, time_column="timestamp"),
        ),
    )
    if evaluation.empty:
        st.info("Waiting for fair price data to evaluate against.")
        return None

    if (evaluation["n"] < _MIN_SAMPLES).all():
        st.info(
            "Collecting data - no horizon has enough samples to evaluate "
            "against yet."
        )
        return None

    return evaluation


def render() -> None:
    evaluation = _evaluation()
    if evaluation is not None:
        _render_verdict(evaluation)


def render_details() -> None:
    """The correlations and slopes the verdict is drawn from. They are
    the card's details rather than something to unfold under it: the
    tables are wide, and the modal gives them room the card cannot."""
    evaluation = _evaluation()
    if evaluation is None:
        return
    _render_correlation(evaluation)
    st.divider()
    _render_slope(evaluation)
