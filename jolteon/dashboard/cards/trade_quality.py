"""How well the session's fills were executed, in tables of averages.

Every table here is one row per side or per inventory bucket however many
fills there are, so the recording works the averages out itself - nothing
here holds a session's fills to average them.
"""

from collections.abc import Mapping

import pandas as pd
import streamlit as st

from jolteon.analysis.markouts import HORIZONS
from jolteon.dashboard.data import trade_queries
from jolteon.dashboard.state import current_run_id
from jolteon.dashboard.ui import table
from jolteon.dashboard.ui.empty_states import warn_if_no_db
from jolteon.dashboard.ui.primitives import SIDE_TINTS, fmt_usd

_HORIZON_PHRASES = {
    "100ms": "100 milliseconds",
    "1s": "1 second",
    "5s": "5 seconds",
    "30s": "30 seconds",
}

_MARKOUT_COLUMNS = [f"Markout +{horizon}" for horizon in HORIZONS]


def _markout_stats(stats: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        f"Markout +{horizon}": stats[f"avg_markout_{horizon}"]
        for horizon in HORIZONS
    }


def _markout_help(context: str) -> dict[str, str]:
    return {
        f"Markout +{horizon}": (
            "How much the price moved in our favor, on average, "
            f"{_HORIZON_PHRASES[horizon]} after {context}."
        )
        for horizon in HORIZONS
    }


def _shaded_table(
    rows: pd.DataFrame,
    money_columns: list[str],
    column_help: Mapping[str, str],
    *,
    shade_side: bool = False,
) -> None:
    table.render(
        rows,
        shaded_columns=money_columns,
        format_fn=fmt_usd,
        column_help=column_help,
        row_style=(
            (lambda row: SIDE_TINTS.get(row["Side"], ""))
            if shade_side
            else None
        ),
    )


def _render_fair_price_movement(
    db_path: str, run_id: str | None = None
) -> None:
    movement = trade_queries.avg_fair_price_movement(db_path, run_id)
    if movement.empty:
        return

    st.markdown("**Fair price movement**")
    columns = [f"+{horizon}" for horizon in HORIZONS]
    rows = pd.DataFrame([movement.values], columns=columns)
    column_help = {
        f"+{horizon}": (
            "Average change in the fair price itself, "
            f"{_HORIZON_PHRASES[horizon]} after a fill - a positive "
            "number means it tends to keep rising, negative means it "
            "tends to fall back."
        )
        for horizon in HORIZONS
    }
    _shaded_table(rows, columns, column_help)


def _render_fill_quality(db_path: str, run_id: str | None = None) -> None:
    """BUY vs SELL execution quality (section 6)."""
    by_side = trade_queries.fill_quality_by_side(db_path, run_id)
    if by_side.empty:
        return

    st.markdown("**Fill Quality**")
    rows = pd.DataFrame(
        {
            "Side": by_side.index,
            "Fills": by_side["fill_count"].astype(int),
            "Average edge": by_side["avg_edge"],
            **_markout_stats(by_side),
        }
    )
    column_help = {
        "Average edge": (
            "How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "on this side."
        ),
        **_markout_help("we filled"),
    }
    _shaded_table(
        rows,
        ["Average edge", *_MARKOUT_COLUMNS],
        column_help,
        shade_side=True,
    )


def _render_inventory_buckets(db_path: str, run_id: str | None = None) -> None:
    """Whether fills made at extreme inventory levels look different from
    fills made near neutral (section 5)."""
    stats = trade_queries.inventory_buckets(db_path, run_id=run_id)
    if stats.empty:
        return

    st.markdown("**Inventory Buckets**")
    rows = pd.DataFrame(
        {
            "Inventory": stats.index,
            "Fills": stats["fill_count"].astype(int),
            "BUY": stats["buy_count"].astype(int),
            "SELL": stats["sell_count"].astype(int),
            "Average edge": stats["avg_edge"],
            **_markout_stats(stats),
        }
    )
    column_help = {
        "Average edge": (
            "How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "made while inventory was in this range."
        ),
        **_markout_help("a fill made while inventory was in this range"),
    }
    _shaded_table(rows, ["Average edge", *_MARKOUT_COLUMNS], column_help)


def render() -> None:
    """Execution quality (section 6, 9) and inventory bucketing (section
    5) - their own card, separate from Orders & PnL's raw fills and cash
    totals."""
    if not warn_if_no_db():
        return

    # Every table on this card is one row per side or per bucket however
    # many fills there are, so the recording works them out itself -
    # nothing here holds a session's fills to average them.
    db_path = st.session_state.db_path
    run_id = current_run_id()
    if not trade_queries.any_fills(db_path, run_id):
        st.info("No fills yet.")
        return

    _render_fill_quality(db_path, run_id)
    _render_inventory_buckets(db_path, run_id)
    _render_fair_price_movement(db_path, run_id)
