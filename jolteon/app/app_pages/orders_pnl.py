import pandas as pd
import streamlit as st

from jolteon.app.components import warn_if_no_db
from jolteon.app.data import read_table

st.title("Orders & PnL")
if not warn_if_no_db():
    st.stop()

db_path = st.session_state.db_path
orders = read_table(db_path, "order")
fills = read_table(db_path, "order_fill")

if fills.empty:
    st.info("No fills yet.")
else:
    signed_qty = fills["quantity"].where(
        fills["side"] == "BUY", -fills["quantity"]
    )
    cash_flow = (-fills["price"] * signed_qty) - fills["fee"]
    by_symbol = (
        pd.DataFrame(
            {
                "symbol": fills["symbol"],
                "position": signed_qty,
                "cash_pnl": cash_flow,
            }
        )
        .groupby("symbol")
        .sum()
    )

    # Cash PnL alone looks worse than reality while inventory is still
    # held: the cash spent buying it shows up as an outflow with
    # nothing offsetting it. Mark held inventory at the latest mid
    # price too, to match PositionManager.total_pnl in the engine.
    bbo = read_table(db_path, "ticker_feed")
    if not bbo.empty:
        latest_mid = bbo.sort_values("timestamp").groupby("symbol").last()
        mark_price = (latest_mid["bid_price"] + latest_mid["ask_price"]) / 2
    else:
        mark_price = pd.Series(dtype=float)
    by_symbol["mark_price"] = by_symbol.index.map(mark_price)
    by_symbol["inventory_value"] = by_symbol["position"] * by_symbol[
        "mark_price"
    ].fillna(0)
    by_symbol["total_pnl"] = (
        by_symbol["cash_pnl"] + by_symbol["inventory_value"]
    )

    st.dataframe(
        by_symbol.rename(
            columns={
                "position": "Position",
                "cash_pnl": "Cash PnL",
                "mark_price": "Mark Price",
                "inventory_value": "Inventory Value",
                "total_pnl": "Total PnL",
            }
        ),
        width="stretch",
    )

    cols = st.columns(2)
    cols[0].metric("Cash PnL", f"{by_symbol['cash_pnl'].sum():.2f}")
    cols[1].metric(
        "Total PnL (mark-to-market)",
        f"{by_symbol['total_pnl'].sum():.2f}",
    )
    st.caption(
        "Cash PnL is money in minus money out across all fills - it "
        "looks worse than reality while inventory is still held, "
        "since nothing offsets the cash spent buying it. Total PnL "
        "adds that inventory back at the latest mid price."
    )

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.caption("Recent orders")
    if orders.empty:
        st.info("No orders placed yet.")
    else:
        st.dataframe(
            orders.sort_values("timestamp", ascending=False).head(20),
            width="stretch",
        )
with col2:
    st.caption("Recent fills")
    if fills.empty:
        st.info("No fills yet.")
    else:
        st.dataframe(
            fills.sort_values("timestamp", ascending=False).head(20),
            width="stretch",
        )
