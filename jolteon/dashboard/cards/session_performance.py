"""The session's marked PnL, charted over time rather than read as a
single number - the same figure the KPI row leads with, watched as it
moves.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from jolteon.analysis.pnl import marked_pnl_over_time
from jolteon.dashboard.cards.orders_pnl import FILLS
from jolteon.dashboard.data.runs import read_run_table
from jolteon.dashboard.data.sqlite import as_datetime
from jolteon.dashboard.state import current_run_id
from jolteon.dashboard.ui.empty_states import warn_if_no_db

BBO_FEED = "bbo_feed"

# The lookback each range button filters the series to, in seconds -
# matching the prototype's 15m/1h/4h buttons.
RANGES: dict[str, float] = {"15m": 15 * 60, "1h": 60 * 60, "4h": 4 * 60 * 60}

_RANGE_KEY = "session-performance-range"


@dataclass(frozen=True)
class SessionPerformanceModel:
    """One refresh's marked-PnL series, timestamp and value."""

    series: pd.DataFrame


def _mid_prices(db_path: str, run_id: str | None) -> pd.DataFrame:
    bbo = read_run_table(db_path, BBO_FEED, run_id)
    if bbo.empty or not {"timestamp", "bid_price", "ask_price"}.issubset(
        bbo.columns
    ):
        return pd.DataFrame(columns=["timestamp", "mid_price"])
    return pd.DataFrame(
        {
            "timestamp": bbo["timestamp"],
            "mid_price": (bbo["bid_price"] + bbo["ask_price"]) / 2,
        }
    )


def load() -> SessionPerformanceModel:
    db_path = st.session_state.db_path
    run_id = current_run_id()
    fills = read_run_table(db_path, FILLS, run_id)
    mid_prices = _mid_prices(db_path, run_id)
    return SessionPerformanceModel(marked_pnl_over_time(fills, mid_prices))


def _windowed(series: pd.DataFrame, choice: str | None) -> pd.DataFrame:
    if choice is None:
        return series
    cutoff = series["timestamp"].max() - RANGES[choice]
    return series[series["timestamp"] >= cutoff]


def render(model: SessionPerformanceModel | None = None) -> None:
    if not warn_if_no_db():
        return

    model = load() if model is None else model
    series = model.series
    if series.empty:
        st.info("No fair prices recorded yet to chart marked PnL against.")
        return

    choice = st.segmented_control(
        "Range",
        options=list(RANGES),
        default=None,
        key=_RANGE_KEY,
        label_visibility="collapsed",
    )
    shown = _windowed(series, choice)

    chart_data = pd.DataFrame(
        {"Marked PnL": shown["marked_pnl"].to_numpy()},
        index=pd.Index(as_datetime(shown["timestamp"]), name="Time"),
    )
    st.line_chart(chart_data, color="green", height=280)
    st.caption(
        "Marked PnL - cash flow plus inventory valued at the recorded "
        "mid - in UTC."
    )
