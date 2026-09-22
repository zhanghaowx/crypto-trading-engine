from dataclasses import dataclass

import pandas as pd
import streamlit as st

from jolteon.dashboard import aggregates, table
from jolteon.dashboard.analytics import HORIZONS
from jolteon.dashboard.components import MISSING, fmt_usd, metric, sign_color
from jolteon.dashboard.data import read_latest_per_group
from jolteon.dashboard.pages.orders_pnl import pnl_by_symbol


@dataclass(frozen=True)
class SessionEconomicsModel:
    """The economics of one engine run used as an analytical window."""

    run_id: str | None
    economics: pd.DataFrame
    marked_pnl: float | None


# Below this a position is round enough to need no mark: a symbol bought
# and sold back in full still leaves a residue of the two quantities.
_FLAT = 1e-12


def _marked_pnl(db_path: str, run_id: str | None) -> float | None:
    """What the run's fills have earned with held inventory marked to the
    latest mid, and nothing at all where inventory is held in a symbol
    nothing was recorded to mark it with - a total missing one of its two
    halves reads as a loss the run did not make."""
    totals = aggregates.position_and_cash(db_path, run_id)
    if totals.empty:
        return None

    marked = pnl_by_symbol(
        totals,
        read_latest_per_group(db_path, "bbo_feed", "symbol", run_id=run_id),
    )
    held = marked["position"].abs() > _FLAT
    if (held & marked["mark_price"].isna()).any():
        return None
    return float(marked["total_pnl"].sum())


def load(db_path: str, run_id: str | None) -> SessionEconomicsModel:
    return SessionEconomicsModel(
        run_id=run_id,
        economics=aggregates.session_economics(db_path, run_id),
        marked_pnl=_marked_pnl(db_path, run_id),
    )


def _bps(value: float) -> str:
    return MISSING if pd.isna(value) else f"{value:+.2f}"


def _cost(value: float) -> str:
    """A fee as the cost it is - unsigned, because the row subtracts it."""
    return MISSING if pd.isna(value) else f"${value:,.2f}"


def _share(measured: float, whole: float) -> str:
    """How much of the run a figure actually rests on.

    A fill with no recorded fair price near enough to measure it against
    is left out of every figure on its row, so a row's dollars and its
    basis points can rest on a fraction of the notional the card reports
    above - which reads as a far smaller edge than was measured unless
    the fraction is shown beside it.
    """
    if pd.isna(measured) or not whole:
        return MISSING
    return f"{measured / whole:.0%}"


def _economics_rows(row: pd.Series) -> pd.DataFrame:
    notional = row["notional"]
    rows = [
        {
            "Horizon": "At fill",
            "Measured": _share(row["measured_notional_at_fill"], notional),
            "Gross": row["gross_edge"],
            "Fees": _cost(row["measured_fees_at_fill"]),
            "Net": row["net_edge"],
            "Gross bps": _bps(row["gross_edge_bps"]),
            "Net bps": _bps(row["net_edge_bps"]),
            "Adverse selection": 0.0,
        }
    ]
    for horizon in HORIZONS:
        rows.append(
            {
                "Horizon": f"+{horizon}",
                "Measured": _share(
                    row[f"measured_notional_{horizon}"], notional
                ),
                "Gross": row[f"gross_markout_{horizon}"],
                "Fees": _cost(row[f"measured_fees_{horizon}"]),
                "Net": row[f"net_markout_{horizon}"],
                "Gross bps": _bps(row[f"gross_markout_bps_{horizon}"]),
                "Net bps": _bps(row[f"net_markout_bps_{horizon}"]),
                "Adverse selection": row[f"adverse_selection_{horizon}"],
            }
        )
    return pd.DataFrame(rows)


def _render_breakdown(row: pd.Series) -> None:
    table.render(
        _economics_rows(row),
        shaded_columns=["Gross", "Net", "Adverse selection"],
        # Already formatted, and in basis points rather than in the
        # dollars `format_fn` speaks - so aligned as numbers, untinted.
        numeric_columns=["Measured", "Fees", "Gross bps", "Net bps"],
        format_fn=fmt_usd,
        column_help={
            "Measured": (
                "Share of the run's notional with a recorded fair price "
                "close enough to measure this row against. Every figure "
                "on the row rests on that share alone."
            ),
            "Gross": "Quantity-weighted markout before trading fees.",
            "Fees": (
                "Fees charged on the fills this row could measure. Gross "
                "less this is Net. The card's own Fees figure is the "
                "whole run's, which is larger wherever a row could not "
                "measure every fill."
            ),
            "Net": "Quantity-weighted markout after those fees.",
            "Gross bps": "Gross markout as basis points of measured notional.",
            "Net bps": "Net markout as basis points of measured notional.",
            "Adverse selection": (
                "How far the fair price moved between the fill and this "
                "horizon, for or against us. The edge taken at the fill "
                "plus this is the markout beside it."
            ),
        },
    )


def render(model: SessionEconomicsModel) -> None:
    if model.economics.empty:
        st.info("No fills in this run.")
        return

    overall = model.economics.loc["ALL"]
    cols = st.columns(4)
    with cols[0]:
        pnl = model.marked_pnl
        st.metric(
            "Marked PnL",
            # Written through the same formatter as the table below, so
            # the sign leads the amount here as it does there.
            MISSING if pnl is None else f":{sign_color(pnl)}[{fmt_usd(pnl)}]",
            border=True,
            help=(
                "Cash the run's fills moved, with anything still held "
                "valued at the latest mid price. Shown only once every "
                "held symbol has a recorded price to value it at."
            ),
        )
    with cols[1]:
        metric(
            "Notional",
            float(overall["notional"]),
            prefix="$",
            border=True,
            help="Price times quantity, added up over every fill.",
        )
    with cols[2]:
        metric(
            "Fees",
            float(overall["fees"]),
            prefix="$",
            border=True,
            help=(
                "Trading fees the exchange charged over the whole run. "
                "Each row below carries the fees of the fills it could "
                "measure."
            ),
        )
    with cols[3]:
        metric(
            "Fills",
            int(overall["fill_count"]),
            decimals=None,
            border=True,
            help="How many of the run's orders were filled.",
        )

    st.markdown("**Execution economics**")
    _render_breakdown(overall)


def render_details(model: SessionEconomicsModel) -> None:
    if model.economics.empty:
        st.info("No fills in this run.")
        return

    for side in ("BUY", "SELL"):
        if side not in model.economics.index:
            continue
        row = model.economics.loc[side]
        fills = int(row["fill_count"])
        st.markdown(
            f"**{side} · {fills} fill{'' if fills == 1 else 's'} · "
            f"${row['notional']:,.2f} notional**"
        )
        _render_breakdown(row)
