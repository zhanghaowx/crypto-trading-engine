"""
Live Streamlit dashboard for the Jolteon trading engine.

This is a read-only viewer: it never talks to the running engine directly.
Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/app/dashboard.py -- --db /tmp/jolteon.sqlite

Note: live runs only flush to the database periodically (see
`enable_auto_save` in jolteon/app/kraken.py), so the dashboard lags behind
the engine by roughly that interval.
"""

import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.core.health_monitor.heartbeat import HeartbeatLevel

HEARTBEAT_LABELS = {
    HeartbeatLevel.NORMAL.value: "\U0001f7e2 NORMAL",
    HeartbeatLevel.WARN.value: "\U0001f7e1 WARN",
    HeartbeatLevel.ERROR.value: "\U0001f7e0 ERROR",
    HeartbeatLevel.CRITICAL.value: "\U0001f534 CRITICAL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/tmp/jolteon.sqlite")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def read_table(db_path: str, table: str) -> pd.DataFrame:
    try:
        with sqlite3.connect(db_path) as conn:
            return pd.read_sql(f"SELECT * FROM {table}", conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()


def as_datetime(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column, unit="s", utc=True)


def render_market_data(db_path: str) -> None:
    st.subheader("Market Data")
    bbo = read_table(db_path, "ticker_feed")
    candles = read_table(db_path, "calculated_candlestick_feed")

    if bbo.empty:
        st.info("No market data recorded yet.")
    else:
        latest = bbo.sort_values("timestamp").iloc[-1]
        mid = (latest["bid_price"] + latest["ask_price"]) / 2
        cols = st.columns(4)
        cols[0].metric("Symbol", latest.get("symbol", "-"))
        cols[1].metric("Bid", f"{latest['bid_price']:.2f}")
        cols[2].metric("Ask", f"{latest['ask_price']:.2f}")
        cols[3].metric("Mid", f"{mid:.2f}")

    if not candles.empty:
        candles = candles.drop_duplicates(
            subset="start_time", keep="last"
        ).sort_values("start_time")
        chart = candles.set_index(as_datetime(candles["start_time"]))[
            ["close"]
        ]
        st.line_chart(chart)


def render_risk_limits(db_path: str) -> None:
    st.subheader("Risk Limits")
    risk = read_table(db_path, "risk_limit_snapshot")

    if risk.empty:
        st.info(
            "No risk limit data recorded yet "
            "(no strategy is live, or nothing has flushed to disk yet)."
        )
        return

    risk = risk.sort_values("timestamp")
    latest = risk.groupby(["name", "symbol"]).tail(1)

    for _, row in latest.iterrows():
        maximum = row["maximum"]
        utilization = (
            min(abs(row["current"]) / maximum, 1.0) if maximum else 0.0
        )
        st.write(
            f"**{row['name']}** ({row['symbol']}): "
            f"{row['current']:.4f} / ±{maximum:.4f} "
            f"({utilization:.0%})"
        )
        st.progress(utilization)

    with st.expander("History"):
        risk["time"] = as_datetime(risk["timestamp"])
        for (name, symbol), group in risk.groupby(["name", "symbol"]):
            st.caption(f"{name} — {symbol}")
            st.line_chart(group.set_index("time")[["current"]])


def render_orders_and_fills(db_path: str) -> pd.DataFrame:
    st.subheader("Orders & Fills")
    orders = read_table(db_path, "order")
    fills = read_table(db_path, "order_fill")

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Recent orders")
        if orders.empty:
            st.info("No orders placed yet.")
        else:
            st.dataframe(
                orders.sort_values("timestamp", ascending=False).head(20),
                use_container_width=True,
            )
    with col2:
        st.caption("Recent fills")
        if fills.empty:
            st.info("No fills yet.")
        else:
            st.dataframe(
                fills.sort_values("timestamp", ascending=False).head(20),
                use_container_width=True,
            )

    return fills


def render_position_and_pnl(fills: pd.DataFrame) -> None:
    st.subheader("Position & PnL")
    if fills.empty:
        st.info("No fills yet.")
        return

    signed_qty = fills["quantity"].where(
        fills["side"] == "BUY", -fills["quantity"]
    )
    cash_flow = (-fills["price"] * signed_qty) - fills["fee"]
    by_symbol = (
        pd.DataFrame(
            {
                "symbol": fills["symbol"],
                "position": signed_qty,
                "realized_pnl": cash_flow,
            }
        )
        .groupby("symbol")
        .sum()
    )
    st.dataframe(by_symbol, use_container_width=True)
    st.metric("Total Realized PnL", f"{by_symbol['realized_pnl'].sum():.2f}")


def render_health(db_path: str) -> None:
    st.subheader("Health")
    heartbeats = read_table(db_path, "heartbeat")
    if heartbeats.empty:
        st.info("No heartbeats recorded yet.")
        return

    latest = (
        heartbeats.sort_values("timestamp").groupby("sender").tail(1).copy()
    )
    latest["status"] = (
        latest["level"].map(HEARTBEAT_LABELS).fillna(latest["level"])
    )
    latest["last_seen"] = as_datetime(latest["timestamp"])
    st.dataframe(
        latest[["sender", "status", "message", "last_seen"]].sort_values(
            "sender"
        ),
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    args = parse_args()

    st.sidebar.title("Jolteon")
    db_path = st.sidebar.text_input("Database path", value=args.db)
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
    refresh_seconds = st.sidebar.slider("Refresh every (s)", 1, 30, 5)
    st.sidebar.caption(f"Checked at {pd.Timestamp.now(tz='UTC'):%H:%M:%S} UTC")

    st.title("Jolteon — Live Trading Engine")

    if not Path(db_path).exists():
        st.warning(
            f"No database found at `{db_path}` yet. "
            f"Waiting for the engine to start recording..."
        )
    else:
        render_market_data(db_path)
        render_risk_limits(db_path)
        fills = render_orders_and_fills(db_path)
        render_position_and_pnl(fills)
        render_health(db_path)

    if auto_refresh:
        time.sleep(refresh_seconds)
        st.rerun()


main()
